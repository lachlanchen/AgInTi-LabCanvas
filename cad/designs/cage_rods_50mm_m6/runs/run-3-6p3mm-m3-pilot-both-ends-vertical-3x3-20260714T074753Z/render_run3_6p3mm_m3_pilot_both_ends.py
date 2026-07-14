#!/usr/bin/env python3
"""Render run 3 6.30 mm rods with M3 pilot holes."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "cage_rods_run3_6p3mm_m3_pilot_both_ends"
STL = RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.stl"
OUT = RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid_render.png"


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.context.scene.world.color = (0.94, 0.94, 0.92)
    mat = bpy.data.materials.new("satin grey rod")
    mat.diffuse_color = (0.22, 0.50, 0.72, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.70, 0.69, 0.63, 1)
    bsdf.inputs["Roughness"].default_value = 0.58
    bpy.ops.wm.stl_import(filepath=str(STL))
    bpy.context.object.data.materials.append(mat)
    bpy.ops.object.light_add(type="AREA", location=(0, -82, 106))
    bpy.context.object.data.energy = 1000
    bpy.context.object.data.size = 88
    bpy.ops.object.camera_add(location=(66, -90, 76), rotation=(1.03, 0.0, 0.62))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 92
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 25))
    target = bpy.context.object
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    shading = bpy.context.scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "WORLD"
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1800
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
