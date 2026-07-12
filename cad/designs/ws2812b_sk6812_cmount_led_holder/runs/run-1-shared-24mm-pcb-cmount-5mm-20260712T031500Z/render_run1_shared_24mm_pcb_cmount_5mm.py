#!/usr/bin/env python3
"""Render the shared WS2812B/SK6812 C-mount LED holder."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "ws2812b_sk6812_cmount_led_holder_run1"
STL = RUN_DIR / f"PRINT_THIS_{STEM}.stl"
OUT = RUN_DIR / f"PRINT_THIS_{STEM}_render.png"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.58
    return mat


def main() -> None:
    clear_scene()
    bpy.context.scene.world.color = (0.98, 0.98, 0.95)
    holder_mat = material("warm gray printed holder", (0.58, 0.55, 0.48, 1.0))
    bpy.ops.wm.stl_import(filepath=str(STL))
    obj = bpy.context.object
    obj.name = "shared WS2812B SK6812 C-mount holder"
    obj.data.materials.append(holder_mat)

    bpy.ops.object.light_add(type="AREA", location=(42, -58, 68))
    bpy.context.object.data.energy = 1650
    bpy.context.object.data.size = 78
    bpy.ops.object.light_add(type="POINT", location=(-32, 45, 42))
    bpy.context.object.data.energy = 260

    bpy.ops.object.camera_add(location=(58, -76, 54), rotation=(1.03, 0.0, 0.66))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 56
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(5, 0, 0))
    target = bpy.context.object
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target

    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.cavity_valley_factor = 1.4
    bpy.context.scene.display.shading.cavity_ridge_factor = 1.2
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.render.resolution_x = 1700
    bpy.context.scene.render.resolution_y = 1400
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
