#!/usr/bin/env python3
"""Render the Lumileds GT-090101-style cage holder with Blender."""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
HOLDER_STL = ARTIFACT_DIR / "lumileds_gt090101_cage_holder.stl"
RENDER_PATH = ARTIFACT_DIR / "lumileds_gt090101_cage_render.png"
BLEND_PATH = ARTIFACT_DIR / "lumileds_gt090101_cage.blend"


def make_material(name: str, color: tuple[float, float, float, float], roughness: float = 0.55, metallic: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Alpha"].default_value = color[3]
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if color[3] < 1.0:
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
    return mat


def look_at(obj, target: tuple[float, float, float]) -> None:
    loc = Vector(obj.location)
    direction = Vector(target) - loc
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_cylinder(name: str, radius: float, depth: float, location: tuple[float, float, float], material, vertices: int = 96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    black = make_material("printed graphite preview", (0.14, 0.145, 0.14, 1), roughness=0.72)
    silver = make_material("translucent stainless rod proxies", (0.82, 0.80, 0.75, 0.22), roughness=0.22, metallic=0.6)
    green = make_material("Lumileds PCB proxy", (0.02, 0.42, 0.10, 1), roughness=0.5)
    led = make_material("LED ceramic emitter", (0.95, 0.90, 0.70, 1), roughness=0.3)

    bpy.ops.import_mesh.stl(filepath=str(HOLDER_STL))
    holder = bpy.context.object
    holder.name = "lumileds_gt090101_cage_holder"
    holder.data.materials.append(black)
    bpy.ops.object.shade_smooth()

    for x in (-15, 15):
        for y in (-15, 15):
            add_cylinder("6mm cage rod proxy", 3.0, 58.0, (x, y, 0), silver)

    pcb_z = -4.5 + 1.9 - 0.8
    add_cylinder("round Lumileds PCB proxy", 12.0, 1.6, (0, 0, pcb_z), green)
    add_cylinder("Lumileds LED aperture marker", 2.45, 0.75, (0, 0, pcb_z + 1.2), led)

    bpy.ops.object.light_add(type="AREA", location=(0, -35, 55))
    key = bpy.context.object
    key.name = "large softbox"
    key.data.energy = 900
    key.data.size = 60
    bpy.ops.object.light_add(type="POINT", location=(-45, 38, 35))
    fill = bpy.context.object
    fill.name = "fill light"
    fill.data.energy = 180

    bpy.ops.object.camera_add(location=(58, -68, -36))
    cam = bpy.context.object
    look_at(cam, (0, 0, -2))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 76
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "BLENDER_EEVEE"
    bpy.context.scene.eevee.taa_render_samples = 64
    bpy.context.scene.world.color = (0.90, 0.92, 0.94)
    bpy.context.scene.render.resolution_x = 1400
    bpy.context.scene.render.resolution_y = 1100
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
    bpy.context.scene.render.filepath = str(RENDER_PATH)

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.render.render(write_still=True)
    print(RENDER_PATH)


if __name__ == "__main__":
    main()
