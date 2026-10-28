#!/usr/bin/env python3
"""Render the single and four-part 100 mm adapter print packages uncropped."""

import json
import math
import sys
from pathlib import Path

import bpy

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(ROOT / "cad/tools"))
from blender_camera_fit import fit_camera_to_objects


def main():
    data = json.loads((DESIGN / "artifacts/height100_manifest.json").read_text())
    run = DESIGN / "runs" / data["run_name"]
    out = run / "renders"
    out.mkdir(exist_ok=True)
    records = []
    for key, filename in (("single", "single_100mm.png"), ("2x2", "print_grid_2x2_100mm.png")):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.studio_light = "paint.sl"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.background_type = "WORLD"
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = "BOTH"
        scene.world = bpy.data.worlds.new("White")
        scene.world.color = (1, 1, 1)
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "Medium High Contrast"
        scene.render.resolution_x, scene.render.resolution_y = 1700, 2200
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        bpy.ops.wm.stl_import(filepath=str(run / (data["print_packages"][key]["stem"] + ".stl")))
        obj = bpy.context.object
        mat = bpy.data.materials.new("Adapter")
        mat.diffuse_color = (0.22, 0.42, 0.49, 1)
        obj.data.materials.append(mat)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(35)
        normal = obj.modifiers.new("Weighted planar normals", "WEIGHTED_NORMAL")
        normal.keep_sharp = True
        _, bounds = fit_camera_to_objects([obj], direction=(1.6, -2.3, 1.0))
        scene.render.filepath = str(out / filename)
        bpy.ops.render.render(write_still=True)
        records.append({"file": filename, "projected_bounds": bounds, "physical_parts": 1 if key == "single" else 4})
    (out / "camera_validation.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
