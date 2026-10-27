#!/usr/bin/env python3
"""White-background full apparatus and explicitly isolated lower-stack views."""

import json
import sys
from pathlib import Path

import bpy

DESIGN = Path(__file__).resolve().parent
sys.path.insert(0, str(DESIGN))
import render_mount as review


def main():
    data = json.loads((DESIGN / "artifacts/manifest.json").read_text())
    if data.get("configuration") != "horizontal_dual_4f_rotary_analyzer":
        raise RuntimeError("Build the horizontal rotary cascade before rendering")
    run = DESIGN / "runs" / data["run_name"]
    review.OUT = run / "renders"
    review.OUT.mkdir(exist_ok=True)
    review.reset()
    objects = {row["name"]: review.mesh(run / row["mesh"], row["name"], row["color"])
               for row in data["render_components"]}
    evidence = [review.fit_and_render(list(objects.values()), "rotary_horizontal_dual_4f_overview",
                                     direction=(1.15, -2.2, 1.1), resolution=(3000, 3200))]
    upper_names = {name for name in objects if name.startswith(("primary_", "secondary_", "frame_camera_", "event_camera_", "c12880_"))}
    for name, obj in objects.items():
        obj.hide_render = name not in upper_names
    evidence.append(review.fit_and_render([objects[name] for name in upper_names], "horizontal_cascade_detector_detail",
                                         direction=(1.1, -2.2, 1), resolution=(3000, 1900)))
    lower_names = set(data["detail_view"]["included_components"])
    for name, obj in objects.items():
        obj.hide_render = name not in lower_names
    # Appearance only: separate transparent/functional materials from black holders.
    detail_colors = {"tungsten_bulb": (0.95, 0.65, 0.20), "qyh1123_lcd": (0.30, 0.68, 0.76),
                     "lcd_lower_polarizer": (0.20, 0.30, 0.38)}
    for name, color in detail_colors.items():
        objects[name].data.materials.clear()
        objects[name].data.materials.append(review.material(name + " detail", color))
    evidence.append(review.fit_and_render([objects[name] for name in lower_names], "shared_lower_stack_explanatory_detail",
                                         direction=(-1.1, -2, 1.4), resolution=(2400, 2400)))
    (review.OUT / "camera_validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    for obj in objects.values():
        obj.hide_render = False
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 3000, 3200
    review.fit_camera_to_objects(list(objects.values()), direction=(1.15, -2.2, 1.1))
    bpy.ops.wm.save_as_mainfile(filepath=str(run / "rotary_horizontal_dual_4f_scene.blend"))


if __name__ == "__main__":
    main()
