#!/usr/bin/env python3
"""Render the 4x4 spacer-ring print layout."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "cage_spacer_ring_run1_id6p4_od7p4_h5"
STL = RUN_DIR / f"PRINT_THIS_{STEM}_4x4_print_grid.stl"
OUT = RUN_DIR / f"PRINT_THIS_{STEM}_4x4_print_grid_render.png"


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.context.scene.world.color = (0.95, 0.96, 0.96)
    material = bpy.data.materials.new("cyan spacer material")
    material.diffuse_color = (0.16, 0.58, 0.52, 1)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.22, 0.58, 0.70, 1)
    bsdf.inputs["Roughness"].default_value = 0.48
    bpy.ops.wm.stl_import(filepath=str(STL))
    bpy.context.object.data.materials.append(material)
    bpy.ops.object.light_add(type="AREA", location=(20, -55, 70))
    bpy.context.object.data.energy = 950
    bpy.context.object.data.size = 70
    bpy.ops.object.camera_add(location=(54, -68, 58), rotation=(0.98, 0.0, 0.66))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 58
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 2.5))
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
    bpy.context.scene.render.resolution_y = 1400
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
