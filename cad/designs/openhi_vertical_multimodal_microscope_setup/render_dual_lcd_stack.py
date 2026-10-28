#!/usr/bin/env python3
"""Render all revised apparatus branches and the unobscured shared lower train."""

import json
import sys
from pathlib import Path

import bpy

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(DESIGN.parent / "yxra100_servo_analyzer_breadboard_mount"))
import render_mount as review

COLORS = {"polymer": (0.10, 0.13, 0.15), "polymer_mid": (0.24, 0.28, 0.32),
          "metal": (0.67, 0.70, 0.73), "glass": (0.30, 0.72, 0.78),
          "pcb": (0.035, 0.32, 0.14), "polarizer": (0.15, 0.30, 0.36),
          "sample": (0.17, 0.68, 0.57), "sensor": (0.72, 0.75, 0.78),
          "lens": (0.31, 0.71, 0.86), "beam_splitter": (0.48, 0.75, 0.89),
          "camera": (0.16, 0.32, 0.48), "event_camera": (0.56, 0.17, 0.13)}


def main():
    latest = json.loads((DESIGN / "artifacts/dual_lcd_stack_latest.json").read_text())
    run = ROOT / latest["run_dir"]
    data = json.loads((run / "manifest.json").read_text())
    review.OUT = run / "renders"
    review.OUT.mkdir(exist_ok=True)
    records = []
    for variant, entry in data["variants"].items():
        review.reset()
        objects = {}
        for row in entry["render_components"]:
            color = COLORS.get(row["category"], row["color"])
            if row["name"] == "tungsten_bulb":
                color = (0.95, 0.65, 0.18)
            objects[row["name"]] = review.mesh(run / row["mesh"], row["name"], color)

        def render(names, filename, direction, resolution):
            for name, obj in objects.items():
                obj.hide_render = name not in names
            selected = [obj for name, obj in objects.items() if name in names]
            record = review.fit_and_render(selected, filename, direction=direction, resolution=resolution)
            record.update({"variant": variant, "visible_components": sorted(names)})
            records.append(record)

        resolution = (3200, 3400) if variant == "dual_4f" else (2600, 3800)
        render(set(objects), f"{variant}_updated_stack_overview", (1.15, -2.2, 0.72), resolution)
        detector_names = {name for name in objects if name.startswith(("primary_4f_", "secondary_4f_", "frame_camera_", "event_camera_", "c12880_", "vertical_cascade"))}
        if variant != "single_4f":
            render(detector_names, f"{variant}_updated_detector_detail", (1.1, -2.2, 0.85), (3000, 2100))
        if variant == "single_4f":
            lower = set(entry["lower_detail_components"])
            render(lower, "updated_lower_optical_stack_detail", (-1.1, -2, 1.0), (2600, 2800))
            render(lower, "updated_lower_optical_stack_opposite", (1.1, 2, 0.95), (2600, 2800))
        for obj in objects.values():
            obj.hide_render = False
        bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = resolution
        review.fit_camera_to_objects(list(objects.values()), direction=(1.15, -2.2, 0.72))
        bpy.ops.wm.save_as_mainfile(filepath=str(run / f"{variant}_updated_stack_scene.blend"))
    (review.OUT / "camera_validation.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
