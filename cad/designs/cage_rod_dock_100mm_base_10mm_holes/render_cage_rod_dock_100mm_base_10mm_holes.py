#!/usr/bin/env python3
"""Render the 100 mm cage rod dock."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_rod_dock_100mm_base_10mm_holes"

DOCK_STL = ARTIFACT_DIR / f"{STEM}.stl"
RENDER = ARTIFACT_DIR / f"{STEM}_render.png"
ASSEMBLY_RENDER = ARTIFACT_DIR / f"{STEM}_assembly_render.png"
BLEND = ARTIFACT_DIR / f"{STEM}.blend"


P = {
    "base_thickness": 30.0,
    "rod_centers": [(-15.0, -15.0), (15.0, -15.0), (-15.0, 15.0), (15.0, 15.0)],
    "rod_diameter": 6.0,
    "rod_depth": 25.0,
    "rod_visible_height": 72.0,
}


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


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def import_stl(path: Path, name: str, material):
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.clear()
    obj.data.materials.append(material)
    return obj


def add_cylinder_z(name: str, radius: float, depth: float, location: tuple[float, float, float], material, vertices: int = 96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def setup_common() -> dict[str, object]:
    clear_scene()
    materials = {
        "dock": make_material("matte graphite dock", (0.17, 0.17, 0.16, 1.0), roughness=0.66),
        "rod": make_material("transparent blue cage rods", (0.08, 0.48, 0.95, 0.42), roughness=0.28),
    }

    bpy.ops.object.light_add(type="AREA", location=(-50, -80, 110))
    key = bpy.context.object
    key.name = "large softbox"
    key.data.energy = 5200
    key.data.size = 22.0

    bpy.ops.object.light_add(type="AREA", location=(72, 58, 72))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 1500
    fill.data.size = 18.0

    bpy.ops.object.camera_add(location=(105, -132, 88), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (0, 0, 18))
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 48
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1700
    bpy.context.scene.render.resolution_y = 1250
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
    bpy.context.scene.view_settings.exposure = 0.8
    bpy.context.scene.view_settings.gamma = 1.0
    bpy.context.scene.world.color = (1, 1, 1)
    return materials


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], *, ortho_scale: float) -> None:
    cam = bpy.context.scene.camera
    cam.location = camera_location
    look_at(cam, target)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_single() -> None:
    materials = setup_common()
    import_stl(DOCK_STL, "100 mm cage rod dock", materials["dock"])
    render(RENDER, (118, -142, 92), (0, 0, 15), ortho_scale=132)


def render_assembly() -> None:
    materials = setup_common()
    import_stl(DOCK_STL, "100 mm cage rod dock", materials["dock"])
    rod_depth = P["rod_depth"] + P["rod_visible_height"]
    rod_center_z = P["base_thickness"] - P["rod_depth"] + rod_depth / 2.0
    for x, y in P["rod_centers"]:
        add_cylinder_z("6 mm cage rod proxy", P["rod_diameter"] / 2.0, rod_depth, (x, y, rod_center_z), materials["rod"])
    render(ASSEMBLY_RENDER, (118, -142, 102), (0, 0, 34), ortho_scale=140)


def main() -> None:
    bpy.context.preferences.filepaths.save_version = 0
    render_single()
    render_assembly()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))


if __name__ == "__main__":
    main()
