#!/usr/bin/env python3
"""Render both exact-fit QYH1123 variants, including their direct-print copies."""

import json
import math
import sys
from pathlib import Path

import bpy

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(ROOT / "cad/tools"))
from blender_camera_fit import fit_camera_to_objects


def load(path, name, color):
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(35)
    normal = obj.modifiers.new("Weighted planar normals", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    return obj


def render(objects, path, direction):
    bpy.context.scene.render.filepath = str(path)
    cam, bounds = fit_camera_to_objects(objects, direction=direction)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return {"file": path.name, "projected_bounds": bounds, "object_count": len(objects)}


def main():
    summary = json.loads((DESIGN / "artifacts/seat45_manifest.json").read_text())
    for key, row in summary["variants"].items():
        run = ROOT / row["run_dir"]
        data = json.loads((run / "manifest.json").read_text())
        out = run / "renders"
        out.mkdir(exist_ok=True)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.studio_light = "paint.sl"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.background_type = "WORLD"
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = "BOTH"
        scene.world = bpy.data.worlds.new("White")
        scene.world.color = (1, 1, 1)
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "Medium High Contrast"
        scene.render.resolution_x = scene.render.resolution_y = 1800
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        holder = load(run / "holder.stl", "holder", (0.22, 0.28, 0.31))
        rows = [render([holder], out / "holder_top.png", (0, 0, 1))]
        valve = load(run / "valve_proxy.stl", "LCD_and_pins_reference", (0.24, 0.70, 0.79))
        rods = load(run / "rods_proxy.stl", "cage_rods_reference", (0.57, 0.65, 0.72))
        rows.append(render([holder, valve, rods], out / "assembly.png", (1.1, -1.6, 1.8)))
        for obj in (holder, valve, rods):
            obj.hide_render = True
        printable = load(run / (data["print_validation"]["stem"] + ".stl"), "print_holder_only", (0.22, 0.42, 0.49))
        rows.append(render([printable], out / "direct_print.png", (1.1, -1.6, 1.8)))
        (out / "camera_validation.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
