#!/usr/bin/env python3
"""Render run 2 combined print plate."""

from __future__ import annotations

from mathutils import Vector
from pathlib import Path

import bpy


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_combo_run2_3x3rods_3x3connectors_2x2adapters"
STL = ARTIFACT_DIR / f"{STEM}.stl"
RENDER = ARTIFACT_DIR / f"{STEM}_render.png"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.55
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners))),
        Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners))),
    )


def setup_scene() -> None:
    clear_scene()
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.show_shadows = True
    bpy.context.scene.world = bpy.data.worlds.new("World") if bpy.context.scene.world is None else bpy.context.scene.world
    bpy.context.scene.world.color = (1.0, 1.0, 1.0)
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1250
    bpy.ops.object.light_add(type="AREA", location=(95, -115, 145))
    light = bpy.context.object
    light.name = "large_softbox"
    light.data.energy = 460
    light.data.size = 72
    bpy.ops.object.camera_add(location=(135, -130, 115))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 180
    bpy.context.scene.camera = camera


def add_ground(center: tuple[float, float, float]) -> None:
    ground_mat = material("matte_ground", (0.88, 0.90, 0.92, 1.0))
    bpy.ops.mesh.primitive_plane_add(size=220, location=(center[0], center[1], -0.03))
    ground = bpy.context.object
    ground.name = "print_plate_ground"
    ground.data.materials.append(ground_mat)


def main() -> None:
    if not STL.exists():
        raise SystemExit(f"Missing STL input: {STL}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    setup_scene()
    mat = material("warm_gray_printed_parts", (0.68, 0.68, 0.64, 1.0))
    bpy.ops.import_mesh.stl(filepath=str(STL))
    obj = bpy.context.object
    obj.name = STEM
    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    min_v, max_v = world_bounds(obj)
    center = ((min_v.x + max_v.x) / 2.0, (min_v.y + max_v.y) / 2.0, (min_v.z + max_v.z) / 2.0)
    add_ground(center)
    camera = bpy.context.scene.camera
    look_at(camera, (center[0], center[1], 25.0))
    camera.data.ortho_scale = max(max_v.x - min_v.x, max_v.y - min_v.y) * 1.18
    bpy.context.scene.render.filepath = str(RENDER)
    bpy.ops.render.render(write_still=True)
    print(RENDER)


if __name__ == "__main__":
    main()
