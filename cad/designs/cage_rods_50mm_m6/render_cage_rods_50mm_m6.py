#!/usr/bin/env python3
"""Render previews for the 50 mm M6/6 mm cage rod design."""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_rods_50mm_m6"

PARAMS = json.loads((ARTIFACT_DIR / "manifest.json").read_text(encoding="utf-8"))["parameters"]


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def add_material(name: str, color: tuple[float, float, float, float], metallic: float = 0.0) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = 0.34
    return material


def add_rod(name: str, x: float, y: float, z_base: float, length: float, material: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=PARAMS["rod_radius_mm"], depth=length, location=(x, y, z_base + length / 2.0))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    bevel = obj.modifiers.new("small_end_bevel", "BEVEL")
    bevel.width = PARAMS["end_chamfer_mm"]
    bevel.segments = 3
    bevel.affect = "EDGES"
    obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
    return obj


def add_horizontal_rod(name: str, location: tuple[float, float, float], material: bpy.types.Material) -> bpy.types.Object:
    obj = add_rod(name, 0, 0, 0, PARAMS["rod_length_mm"], material)
    obj.rotation_euler[1] = math.radians(90)
    obj.location = location
    return obj


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_camera(location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> None:
    bpy.ops.object.light_add(type="AREA", location=(0, -68, 95))
    bpy.context.object.name = "large_softbox"
    bpy.context.object.data.energy = 680
    bpy.context.object.data.size = 80

    bpy.ops.object.camera_add(location=location, rotation=(0, 0, 0))
    bpy.context.scene.camera = bpy.context.object
    look_at(bpy.context.object, target)
    bpy.context.object.data.type = "ORTHO"
    bpy.context.object.data.ortho_scale = ortho_scale

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 96
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.world.color = (1.0, 1.0, 1.0)


def add_reference_floor(size: float = 92.0) -> None:
    mat = add_material("matte_floor", (0.86, 0.87, 0.84, 1.0), 0.0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.35))
    floor = bpy.context.object
    floor.name = "reference_floor"
    floor.dimensions = (size, size, 0.7)
    floor.data.materials.append(mat)


def render_assembly(path: Path) -> None:
    clear_scene()
    rod_mat = add_material("brushed_aluminum_rods", (0.70, 0.70, 0.66, 1.0), 0.45)
    add_reference_floor(72)
    for index, (x, y) in enumerate(PARAMS["rod_centers_mm"], start=1):
        add_rod(f"50mm_m6_cage_rod_{index}", x, y, 0, PARAMS["rod_length_mm"], rod_mat)
    setup_camera((74, -92, 78), (0, 0, 27), 78)
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACT_DIR / f"{STEM}.blend"))
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_single(path: Path) -> None:
    clear_scene()
    rod_mat = add_material("brushed_aluminum_single", (0.70, 0.70, 0.66, 1.0), 0.45)
    add_reference_floor(76)
    add_horizontal_rod("single_50mm_m6_cage_rod", (0, 0, 9), rod_mat)
    setup_camera((58, -68, 42), (0, 0, 8), 68)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    render_single(ARTIFACT_DIR / f"{STEM}_render.png")
    render_assembly(ARTIFACT_DIR / f"{STEM}_assembly_render.png")


if __name__ == "__main__":
    main()
