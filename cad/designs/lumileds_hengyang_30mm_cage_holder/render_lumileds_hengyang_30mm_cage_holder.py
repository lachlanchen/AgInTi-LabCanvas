#!/usr/bin/env python3
"""Render the independent Lumileds Hengyang-style 30 mm cage holder."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
HOLDER_STL = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder.stl"
RENDER_PATH = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder_render.png"
BLEND_PATH = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder.blend"


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
    direction = Vector(target) - Vector(obj.location)
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

    holder_mat = make_material("graphite preview holder", (0.43, 0.43, 0.40, 1.0), roughness=0.65)
    pcb_mat = make_material("green Lumileds PCB proxy", (0.02, 0.36, 0.10, 1.0), roughness=0.5)
    led_mat = make_material("warm LED emitter marker", (1.0, 0.88, 0.50, 1.0), roughness=0.25)

    bpy.ops.import_mesh.stl(filepath=str(HOLDER_STL))
    holder = bpy.context.object
    holder.name = "independent_lumileds_30mm_cage_holder"
    holder.data.materials.append(holder_mat)
    bpy.ops.object.shade_smooth()

    pcb_z = -5.5 + 2.05 - 0.8
    add_cylinder("rear Lumileds PCB proxy", 12.0, 1.6, (0, 0, pcb_z), pcb_mat)
    add_cylinder("LED aperture/emitter marker", 2.5, 0.75, (0, 0, pcb_z + 1.2), led_mat)

    bpy.ops.object.light_add(type="AREA", location=(45, -55, -42))
    key = bpy.context.object
    key.name = "rear-side softbox"
    key.data.energy = 5200
    key.data.size = 58
    bpy.ops.object.light_add(type="AREA", location=(-40, 32, 42))
    fill = bpy.context.object
    fill.name = "fill light"
    fill.data.energy = 1400
    fill.data.size = 50

    bpy.ops.object.camera_add(location=(58, -68, -34))
    camera = bpy.context.object
    look_at(camera, (0, 0, -2.0))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 76
    bpy.context.scene.camera = camera

    bpy.context.scene.render.engine = "BLENDER_EEVEE"
    bpy.context.scene.eevee.taa_render_samples = 64
    bpy.context.scene.eevee.use_gtao = True
    bpy.context.scene.eevee.gtao_distance = 4
    bpy.context.scene.eevee.gtao_factor = 0.65
    bpy.context.scene.world.color = (0.98, 0.985, 0.99)
    bpy.context.scene.render.resolution_x = 1500
    bpy.context.scene.render.resolution_y = 1120
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
    bpy.context.scene.view_settings.exposure = 0.7
    bpy.context.scene.render.filepath = str(RENDER_PATH)

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.render.render(write_still=True)
    print(RENDER_PATH)


if __name__ == "__main__":
    main()
