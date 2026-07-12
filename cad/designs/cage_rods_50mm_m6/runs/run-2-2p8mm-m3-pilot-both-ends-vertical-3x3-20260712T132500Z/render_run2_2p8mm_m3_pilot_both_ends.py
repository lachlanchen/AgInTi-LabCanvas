#!/usr/bin/env python3
"""Render run 2 rods with 2.8 mm M3 pilot holes."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "cage_rods_run2_2p8mm_m3_pilot_both_ends"
STL = RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.stl"
OUT = RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid_render.png"


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.context.scene.world.color = (0.94, 0.94, 0.92)
    mat = bpy.data.materials.new("satin grey rod")
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
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 64
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1800
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
