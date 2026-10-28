#!/usr/bin/env python3
"""Inspect the through-pin window from the LCD face, rear and connector side."""

import json
import math
import sys
from pathlib import Path

import bpy

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(ROOT / "cad/tools"))
from blender_camera_fit import fit_camera_to_objects


def mesh(path, name, color):
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.data.use_auto_smooth = True
    obj.data.auto_smooth_angle = math.radians(35)
    modifier = obj.modifiers.new("Weighted planar normals", "WEIGHTED_NORMAL")
    modifier.keep_sharp = True
    return obj


def view(objects, path, direction):
    visible = set(objects)
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            obj.hide_render = obj not in visible
    cam, bounds = fit_camera_to_objects(objects, direction=direction)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return {"file": path.name, "projected_bounds": bounds, "visible_objects": [obj.name for obj in objects]}


def main():
    summary = json.loads((DESIGN / "artifacts/pin_clearance_manifest.json").read_text())
    for variant in summary["variants"].values():
        run = ROOT / variant["run_dir"]
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
        scene.render.resolution_x = scene.render.resolution_y = 1900
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        objects = {row["name"]: mesh(run / row["mesh"], row["name"], row["color"]) for row in data["render_parts"]}
        records = [view([objects["holder"]], out / "LCD_face_top.png", (0, 0, 1)),
                   view([objects["holder"]], out / "rear_through_clearance.png", (1.4, -1.8, -1.6)),
                   view(list(objects.values()), out / "rear_connector_envelope_reference.png", (1.3, -1.8, -1.4))]
        printable = mesh(run / (data["print_validation"]["stem"] + ".stl"), "print_holder_only", (0.22, 0.42, 0.49))
        records.append(view([printable], out / "direct_print.png", (1.2, -1.7, 1.6)))
        (out / "camera_validation.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
