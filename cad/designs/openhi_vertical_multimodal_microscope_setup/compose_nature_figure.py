#!/usr/bin/env python3
"""Compose editable-vector labels around the verified CAD renders."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image


DESIGN_DIR = Path(__file__).resolve().parent
RENDER_DIR = DESIGN_DIR / "artifacts" / "renders"
FIGURE_DIR = DESIGN_DIR / "artifacts" / "figures"


def main() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    panels = [
        ("a", "Single-relay apparatus", RENDER_DIR / "single_4f_nature.png"),
        ("b", "Source, modulator and sample stack", RENDER_DIR / "single_4f_lower_stack_detail.png"),
        ("c", "Cascaded dual-relay apparatus", RENDER_DIR / "dual_4f_nature.png"),
        ("d", "Three-detector output architecture", RENDER_DIR / "dual_4f_detector_detail.png"),
    ]
    missing = [str(path) for _, _, path in panels if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing renders: " + ", ".join(missing))

    fig = plt.figure(figsize=(7.10, 7.45), facecolor="white")
    grid = fig.add_gridspec(2, 2, left=0.035, right=0.985, bottom=0.115, top=0.965, wspace=0.035, hspace=0.105)
    for (letter, title, path), slot in zip(panels, grid):
        ax = fig.add_subplot(slot)
        ax.imshow(Image.open(path))
        ax.set_axis_off()
        label_box = {"facecolor": "white", "edgecolor": "none", "alpha": 0.86, "pad": 1.7}
        ax.text(
            0.012,
            0.985,
            letter,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=11,
            fontweight="bold",
            color="#111111",
            bbox=label_box,
        )
        ax.text(
            0.075,
            0.985,
            title,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=7.2,
            fontweight="semibold",
            color="#222222",
            bbox=label_box,
        )

    caption = (
        "CAD reconstruction of the vertical spectral-polarization microscope. The common lower train combines a tungsten source, "
        "QYH1123 liquid-crystal valve, sample stage, GT090101 analyzer and OpenHI microscope. The single-relay form records a frame "
        "image and one spectral output; the cascaded form preserves the frame branch and adds event-camera and C12880MA outputs. "
        "Camera housings, sample volume and the thin LCD polarizer are visualization proxies; optical holders and relay bodies reuse the accepted CAD."
    )
    fig.text(0.04, 0.035, caption, ha="left", va="bottom", fontsize=7.2, color="#252525", wrap=True)
    for suffix in ("png", "pdf", "svg"):
        target = FIGURE_DIR / f"Figure_1_vertical_multimodal_openhi_setup.{suffix}"
        fig.savefig(target, dpi=300 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    vertical = [
        ("a", "Vertically cascaded relays", RENDER_DIR / "dual_4f_vertical_nature.png", [0.025, 0.14, 0.46, 0.82]),
        ("b", "Complete detector branches", RENDER_DIR / "dual_4f_vertical_detector_detail.png", [0.51, 0.53, 0.47, 0.43]),
        ("c", "Source and sample stack", RENDER_DIR / "single_4f_lower_stack_detail.png", [0.51, 0.14, 0.47, 0.35]),
    ]
    fig = plt.figure(figsize=(7.1, 8.6), facecolor="white")
    for letter, title, path, rectangle in vertical:
        ax = fig.add_axes(rectangle)
        ax.imshow(Image.open(path))
        ax.set_axis_off()
        ax.set_title(f"{letter}  {title}", loc="left", fontsize=8, fontweight="bold", pad=7)
    caption = (
        "Vertical cascade of two accepted OpenHI relays. The first lateral port records the frame-camera branch; "
        "the second relay provides the event-camera and C12880MA branches. The 3 mm interface gap and each relay's "
        "0.367 mm beam-splitter axis compensation are retained. All detectors are shown within the image bounds. "
        "The lower-stack detail is unchanged. Camera housings and short adapters are visualization proxies."
    )
    fig.text(0.035, 0.025, caption, ha="left", va="bottom", fontsize=7.2, color="#252525", wrap=True)
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(FIGURE_DIR / f"Figure_2_vertical_cascade_openhi_setup.{suffix}",
                    dpi=300 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
