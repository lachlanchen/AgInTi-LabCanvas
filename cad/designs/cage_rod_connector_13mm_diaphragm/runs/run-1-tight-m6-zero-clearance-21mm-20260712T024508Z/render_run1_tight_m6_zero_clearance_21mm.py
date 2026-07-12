#!/usr/bin/env python3
"""Render run 1 tight connector print grid."""

from __future__ import annotations

from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
STEM = "cage_rod_connector_run1_tight_m6_zero_clearance_21mm"
STL = RUN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid.stl"
OUT = RUN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid_render.png"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def make_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.56
    return mat


def import_stl(path: Path, material: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.name = path.stem
    obj.data.materials.append(material)
    return obj


def fit_camera(obj: bpy.types.Object) -> None:
    bpy.ops.object.light_add(type="AREA", location=(0, -50, 72))
    bpy.context.object.data.energy = 450
    bpy.context.object.data.size = 70
    bpy.ops.object.camera_add(location=(58, -74, 54), rotation=(1.05, 0.0, 0.66))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 72
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 8))
    target = bpy.context.object
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target


def main() -> None:
    clear_scene()
    bpy.context.scene.world.color = (0.78, 0.78, 0.76)
    mat = make_material("matte graphite connector", (0.24, 0.235, 0.22, 1))
    obj = import_stl(STL, mat)
    fit_camera(obj)
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 64
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1400
    bpy.context.scene.render.filepath = str(OUT)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
