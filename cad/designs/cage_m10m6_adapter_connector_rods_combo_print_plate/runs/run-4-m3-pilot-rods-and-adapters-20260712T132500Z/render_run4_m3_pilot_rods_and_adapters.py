#!/usr/bin/env python3
"""Render run 4 M3-pilot rods and adapter print plate."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "cage_combo_run4_m3_pilot_rods_and_adapters"
STL = RUN_DIR / f"PRINT_THIS_{STEM}.stl"
OUT = RUN_DIR / f"PRINT_THIS_{STEM}_render.png"


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.context.scene.world.color = (0.94, 0.94, 0.92)
    mat = bpy.data.materials.new("combo matte material")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.68, 0.65, 0.58, 1)
    bsdf.inputs["Roughness"].default_value = 0.58
    bpy.ops.wm.stl_import(filepath=str(STL))
    bpy.context.object.data.materials.append(mat)
    bpy.ops.object.light_add(type="AREA", location=(55, -95, 118))
    bpy.context.object.data.energy = 1450
    bpy.context.object.data.size = 105
    bpy.ops.object.camera_add(location=(95, -122, 92), rotation=(1.04, 0.0, 0.70))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 120
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(42, 16, 34))
    target = bpy.context.object
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 64
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.render.resolution_x = 1900
    bpy.context.scene.render.resolution_y = 1500
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
