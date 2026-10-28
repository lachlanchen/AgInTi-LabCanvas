#!/usr/bin/env python3
"""Prepare and publish a rendering-only revision of the accepted apparatus."""

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
POINTER = DESIGN / "artifacts/publication_latest.json"
NUTSTORE = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
TITLES = {"single_4f": "Single-relay configuration", "dual_4f": "Horizontal cascade",
          "dual_4f_vertical": "Vertical cascade"}
ACCENTS = {"Frame camera": "#256b90", "Event camera": "#b45b33", "Spectrometer": "#237867"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flatten_png(file):
    if not file.resolve().is_relative_to(DESIGN / "runs"):
        raise ValueError("Only generated project-run images may be flattened")
    image = Image.open(file).convert("RGBA")
    white = Image.new("RGBA", image.size, (255, 255, 255, 255))
    Image.alpha_composite(white, image).convert("RGB").save(file)


def prepare():
    previous = json.loads((DESIGN / "artifacts/dual_lcd_stack_latest.json").read_text())
    source = ROOT / previous["run_dir"]
    accepted = json.loads((source / "manifest.json").read_text())
    nums = [int(match.group(1)) for folder in (DESIGN / "runs").iterdir()
            if (match := re.match(r"run-(\d+)-", folder.name))]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = DESIGN / "runs" / f"run-{max(nums) + 1}-publication-studio-render-{stamp}"
    run.mkdir()
    variants = {}
    for name, entry in accepted["variants"].items():
        step = source / entry["assembly_step"]
        shutil.copy2(step, run / step.name)
        rows = []
        for row in entry["render_components"]:
            file = source / row["mesh"]
            rows.append({**row, "source_mesh": str(file.relative_to(ROOT)), "sha256": sha(file)})
        variants[name] = {"assembly_step": step.name, "sha256": sha(step),
                          "render_components": rows, "lower_detail_components": entry["lower_detail_components"]}
    data = {"run_name": run.name, "source_run": str(source.relative_to(ROOT)),
            "source_manifest_sha256": sha(source / "manifest.json"), "cad_geometry_changed": False,
            "variants": variants, "render_settings": {
                "engine": "CYCLES", "device": "CPU", "threads": 6, "samples": 64,
                "adaptive_threshold": 0.04, "denoise": True, "source_mm_to_scene_m": 0.001,
                "background": "white", "camera": "orthographic, verified 8 percent margin",
                "render_only_edge_softening_mm": 0.15,
            }, "limitations": accepted["limitations"]}
    (run / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    POINTER.write_text(json.dumps({"run_dir": str(run.relative_to(ROOT)), "manifest": str((run / "manifest.json").relative_to(ROOT)),
                                  "source_run": data["source_run"], "cad_geometry_changed": False}, indent=2) + "\n")
    print(run)


def image_panel(fig, rectangle, file):
    image = Image.open(file)
    ax = fig.add_axes(rectangle)
    ax.imshow(image, extent=(0, 1, 0, 1), aspect="auto")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    return ax


def label(ax, point, text, xytext, color="#30383d", align="left", detector=False):
    straight = abs(point[1] - xytext[1]) < 1e-4 or abs(point[0] - xytext[0]) < 1e-4
    connection = "angle,angleA=90,angleB=0,rad=3" if detector else "angle,angleA=0,angleB=90,rad=3"
    ax.annotate(text, xy=point, xytext=xytext, xycoords="axes fraction", textcoords="axes fraction",
                fontsize=7, ha=align, va="center", color=color,
                arrowprops={"arrowstyle": "-", "color": "#8c979c", "lw": 0.55,
                            "connectionstyle": "arc3,rad=0" if straight else connection},
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2})
    ax.plot(*point, marker="o", markersize=1.8, color=color, transform=ax.transAxes)


def compose():
    latest = json.loads(POINTER.read_text())
    run = ROOT / latest["run_dir"]
    data = json.loads((run / "manifest.json").read_text())
    records = json.loads((run / "renders/camera_validation.json").read_text())
    views = {row["name"]: row for row in records}
    out = run / "figures"
    out.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "Liberation Sans", "svg.fonttype": "none", "pdf.fonttype": 42})
    layouts = []
    for variant, title in TITLES.items():
        fig = plt.figure(figsize=(7.2, 7.8), facecolor="white")
        fig.text(0.035, 0.965, title, fontsize=11, weight="bold", color="#222a30", va="top")
        # Image boxes retain the render aspect ratio; no stretched geometry.
        over = views[variant + "_overview"]
        detector = views[variant + "_detectors"]
        lower = views["lower_stack_detail"]
        panels = []
        for letter, row, box, heading in (
            ("a", over, (0.025, 0.12, 0.50, 0.78), "Complete apparatus"),
            ("b", detector, (0.55, 0.565, 0.425, 0.32), "Detector branches"),
            ("c", lower, (0.55, 0.14, 0.29, 0.34), "Illumination and specimen"),
        ):
            x, y, w, h = box
            image = Image.open(run / "renders" / row["file"])
            natural = image.width / image.height
            available = w * 7.2 / (h * 7.8)
            if natural < available:
                nw = h * 7.8 * natural / 7.2
                x += (w - nw) / 2
                w = nw
            else:
                nh = w * 7.2 / natural / 7.8
                y += (h - nh) / 2
                h = nh
            ax = image_panel(fig, (x, y, w, h), run / "renders" / row["file"])
            fig.text(box[0], box[1] + box[3] + 0.018, letter, fontsize=10, weight="bold", color="#182127")
            fig.text(box[0] + 0.027, box[1] + box[3] + 0.018, heading, fontsize=8.3, color="#4a555d")
            panels.append({"panel": letter, "render": row["name"], "rectangle": [x, y, w, h], "image_size": image.size})
            if letter == "a":
                for name in ("Relay 2", "Relay 1", "Microscope", "Specimen"):
                    if name in row["anchors"]:
                        point = row["anchors"][name][:2]
                        label(ax, point, name, (0.0, point[1]), align="left")
            if letter == "b":
                anchors = row["anchors"]
                names = sorted((n for n in ("Frame camera", "Spectrometer", "Event camera") if n in anchors), key=lambda n: anchors[n][0])
                # Labels occupy the white margin, not the hardware.
                for i, name in enumerate(names):
                    xpos = (i + 0.5) / len(names)
                    caption = {"Frame camera": "Frame\ncamera", "Event camera": "Event\ncamera", "Spectrometer": "C12880MA"}[name]
                    label(ax, anchors[name][:2], caption, (xpos, -0.06), ACCENTS[name], align="center", detector=True)
            if letter == "c":
                names = [("Upper GT090101", "Analyzer"), ("Upper LCD", "Upper LCD"),
                         ("Specimen", "Specimen"), ("Lower LCD", "Lower LCD"),
                         ("Lower GT090101", "Polarizer"), ("Lamp", "Lamp / PCB")]
                for i, (key, caption) in enumerate(names):
                    label(ax, row["anchors"][key][:2], caption, (1.03, 0.87 - i * 0.14), align="left")
        fig.text(0.035, 0.045, "Accepted CAD geometry. Detail views use independent scales.", fontsize=6.5, color="#69747b")
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        width, height = fig.canvas.get_width_height()
        text_bounds = []
        for text in [*fig.texts, *(t for ax in fig.axes for t in ax.texts)]:
            bounds = text.get_window_extent(renderer)
            if bounds.xmin < 0 or bounds.ymin < 0 or bounds.xmax > width or bounds.ymax > height:
                raise RuntimeError(f"Figure text clipped: {text.get_text()}")
            text_bounds.append({"text": text.get_text(), "bounds_fraction": [bounds.xmin / width, bounds.ymin / height, bounds.xmax / width, bounds.ymax / height]})
        for ext in ("png", "pdf", "svg"):
            fig.savefig(out / f"Figure_{variant}_publication.{ext}", dpi=450, facecolor="white")
        plt.close(fig)
        layouts.append({"variant": variant, "panels": panels, "text_bounds": text_bounds})
    (out / "layout_validation.json").write_text(json.dumps(layouts, indent=2) + "\n")
    (run / "README.md").write_text(
        "# OpenHI apparatus: publication render\n\n"
        "Rendering-only revision of the accepted dual-LCD / dual-GT090101 apparatus. All three STEP assemblies are byte-identical to the source run. No placement, spacer, thread, lens or fixture geometry changes.\n\n"
        "Start with figures/Figure_dual_4f_publication.pdf for the horizontal cascade, Figure_dual_4f_vertical_publication.pdf for the vertical cascade, or Figure_single_4f_publication.pdf. Matching PNG/SVG files retain editable figure labels in the vector formats. Unlabelled renders and editable Blender scenes are included.\n\n"
        "The source millimetres are uniformly converted to metres for lighting. Cycles uses CPU rendering, studio area lights, a white background, soft contact shadows, graphite polymer, satin metal and transmissive optical references. A 0.15 mm render-only edge bevel is used on box-like fixtures/camera proxies; STEP files remain untouched. Colors are illustrative, not calibrated optical properties.\n\n"
        "Every complete overview includes all detector branches with an 8% camera margin. Lower-stack details only hide the microscope/relays/detectors. Camera housings and spacing assumptions remain visualization references, not new manufacturing or optical-performance validation.\n")
    sources = run / "source"
    sources.mkdir(exist_ok=True)
    for file in (Path(__file__), DESIGN / "render_publication.py", DESIGN / "README.md", ROOT / "tests/test_openhi_publication_render.py"):
        if file.exists():
            shutil.copy2(file, sources / file.name)
    # Only a checked, complete final render may be delivered as publication output.
    expected = {v + suffix for v in TITLES for suffix in ("_overview", "_detectors")} | {"lower_stack_detail", "lower_stack_opposite"}
    if set(views) != expected:
        raise RuntimeError("Incomplete publication view set")
    for view in records:
        b = view["projected_bounds"]
        if not (0.079 <= b["xmin"] < b["xmax"] <= 0.921 and 0.079 <= b["ymin"] < b["ymax"] <= 0.921):
            raise RuntimeError("Unsafe apparatus framing")
    for variant, row in data["variants"].items():
        if sha(run / row["assembly_step"]) != row["sha256"]:
            raise RuntimeError("Rendering changed the accepted STEP")
    target = NUTSTORE / DESIGN.name / run.name
    checksums = {}
    for file in sorted(run.rglob("*")):
        if not file.is_file() or file.suffix == ".blend1" or file.name == "sync_manifest.json" or "previews" in file.parts:
            continue
        relative = file.relative_to(run)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, output)
        checksums[str(relative)] = sha(file)
        if sha(output) != checksums[str(relative)]:
            raise RuntimeError(f"Copy mismatch: {relative}")
    (run / "sync_manifest.json").write_text(json.dumps(checksums, indent=2) + "\n")
    shutil.copy2(run / "sync_manifest.json", target / "sync_manifest.json")
    print(json.dumps({"nutstore": str(target), "files": len(checksums)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--flatten", type=Path)
    args = parser.parse_args()
    if args.flatten:
        flatten_png(args.flatten)
    elif args.prepare:
        prepare()
    else:
        compose()
