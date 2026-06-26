#!/usr/bin/env python3
"""Render the simple PCB-aligned Lumileds cage holder."""

from __future__ import annotations

from math import radians
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "lumileds_pcb_aligned_simple_cage_holder"
HOLDER_STL = ARTIFACT_DIR / f"{STEM}.stl"
RENDER_PATH = ARTIFACT_DIR / f"{STEM}_render.png"
TOP_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_top_alignment_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


P = {
    "body_width": 42.0,
    "body_height": 42.0,
    "body_thickness": 8.0,
    "pcb_diameter": 24.0,
    "pcb_thickness": 1.6,
    "rod_pitch": 30.0,
    "rod_diameter": 5.9,
    "m2_points": [(-6.0, -6.0), (6.0, -6.0), (-6.0, 6.0), (6.0, 6.0)],
    "pin_points": [(10.0, 1.0), (10.0, -1.54)],
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


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_cylinder_z(name: str, radius: float, depth: float, location: tuple[float, float, float], material, vertices: int = 96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def add_box(name: str, dimensions: tuple[float, float, float], location: tuple[float, float, float], material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def setup_scene() -> dict[str, object]:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    materials = {
        "holder": make_material("matte dark gray printed holder", (0.18, 0.18, 0.17, 1.0), roughness=0.65),
        "pcb": make_material("transparent green PCB proxy", (0.02, 0.42, 0.12, 0.68), roughness=0.48),
        "led": make_material("warm LED emitter proxy", (1.0, 0.78, 0.18, 1.0), roughness=0.2),
        "rod": make_material("blue cage rod alignment proxies", (0.15, 0.45, 0.9, 0.48), roughness=0.34),
        "screw": make_material("silver M2 alignment pins", (0.82, 0.82, 0.78, 0.86), roughness=0.28, metallic=0.45),
        "pin": make_material("gold header pin alignment", (0.95, 0.58, 0.16, 0.95), roughness=0.22, metallic=0.65),
        "header": make_material("black 2P header body proxy", (0.01, 0.01, 0.012, 1.0), roughness=0.44),
    }

    bpy.ops.import_mesh.stl(filepath=str(HOLDER_STL))
    holder = bpy.context.object
    holder.name = "single_piece_holder_from_stl"
    holder.data.materials.clear()
    holder.data.materials.append(materials["holder"])

    rear_face_z = -P["body_thickness"] / 2.0
    pcb_center_z = rear_face_z - P["pcb_thickness"] / 2.0
    add_cylinder_z("PCB proxy: centered by KiCad holes", P["pcb_diameter"] / 2.0, P["pcb_thickness"], (0, 0, pcb_center_z), materials["pcb"])
    add_cylinder_z("LED emitter at PCB origin", 2.35, 0.8, (0, 0, rear_face_z + 0.36), materials["led"])

    rod_half = P["rod_pitch"] / 2.0
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            add_cylinder_z("30 mm cage rod alignment", P["rod_diameter"] / 2.0, P["body_thickness"] + 5.0, (x, y, 0), materials["rod"])

    for index, (x, y) in enumerate(P["m2_points"], start=1):
        add_cylinder_z(f"M2 PCB hole alignment pin {index}", 1.05, P["body_thickness"] + P["pcb_thickness"] + 2.0, (x, y, -0.8), materials["screw"], vertices=48)

    for index, (x, y) in enumerate(P["pin_points"], start=1):
        add_cylinder_z(f"2P header pin relief {index}", 0.45, P["body_thickness"] + P["pcb_thickness"] + 1.4, (x, y, -0.9), materials["pin"], vertices=32)

    add_box("right-angle 2P header body proxy", (5.2, 6.4, 2.5), (12.2, -0.27, rear_face_z - P["pcb_thickness"] - 1.25), materials["header"])

    bpy.ops.object.light_add(type="AREA", location=(0, -35, 45))
    light = bpy.context.object
    light.name = "large softbox"
    light.data.energy = 850
    light.data.size = 5.5
    bpy.ops.object.light_add(type="AREA", location=(-32, 26, 30))
    fill = bpy.context.object
    fill.name = "alignment fill light"
    fill.data.energy = 260
    fill.data.size = 9.0

    bpy.ops.object.camera_add(location=(39, -49, 34), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (0, 0, -1.2))
    cam.data.lens = 58
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 48
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 0
    bpy.context.scene.view_settings.gamma = 1
    bpy.context.scene.world.color = (1, 1, 1)

    return materials


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], lens: float, ortho: bool = False, ortho_scale: float = 48.0) -> None:
    cam = bpy.context.scene.camera
    cam.location = camera_location
    look_at(cam, target)
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    else:
        cam.data.type = "PERSP"
        cam.data.lens = lens
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    setup_scene()
    render(RENDER_PATH, (39, -49, 34), (0, 0, -1.2), 58)
    render(TOP_RENDER_PATH, (0, 0, 70), (0, 0, -1.2), 58, ortho=True, ortho_scale=48)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
