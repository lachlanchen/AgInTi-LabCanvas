#!/usr/bin/env python3
"""Render run 5 adapter, rod, and spacer direct-print plate."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "cage_combo_run5_6p3_adapters_rods_id6p4_od7p4_spacers"
STL = RUN_DIR / f"PRINT_THIS_{STEM}.stl"
OUT = RUN_DIR / f"PRINT_THIS_{STEM}_render.png"


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.context.scene.world.color = (0.94, 0.94, 0.92)
    mat = bpy.data.materials.new("combo matte material")
    mat.diffuse_color = (0.62, 0.40, 0.72, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.68, 0.65, 0.58, 1)
    bsdf.inputs["Roughness"].default_value = 0.58
    bpy.ops.wm.stl_import(filepath=str(STL))
    bpy.context.object.data.materials.append(mat)
    bpy.ops.object.light_add(type="AREA", location=(70, -115, 130))
    bpy.context.object.data.energy = 1450
    bpy.context.object.data.size = 125
    bpy.ops.object.camera_add(location=(125, -158, 112), rotation=(1.04, 0.0, 0.70))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 170
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(70, 21, 34))
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
    bpy.context.scene.render.resolution_x = 2100
    bpy.context.scene.render.resolution_y = 1300
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
