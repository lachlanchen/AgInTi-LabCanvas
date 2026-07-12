#!/usr/bin/env python3
"""Render run 3 exact combo print plate."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters"
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
    bpy.context.scene.world.color = (0.94, 0.94, 0.92)
    mat = material("combo matte material", (0.68, 0.66, 0.6, 1))
    bpy.ops.wm.stl_import(filepath=str(STL))
    bpy.context.object.data.materials.append(mat)
    bpy.ops.object.light_add(type="AREA", location=(55, -95, 118))
    bpy.context.object.data.energy = 1500
    bpy.context.object.data.size = 105
    bpy.ops.object.camera_add(location=(110, -130, 100), rotation=(1.04, 0.0, 0.72))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 150
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(62, 18, 35))
    target = bpy.context.object
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 64
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.render.resolution_x = 2000
    bpy.context.scene.render.resolution_y = 1500
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
