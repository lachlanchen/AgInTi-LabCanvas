#!/usr/bin/env python3
"""Render the Lumileds holder variant with 2P right-angle header clearance."""

from __future__ import annotations

from math import radians
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "lumileds_hengyang_30mm_cage_holder_2p_right_angle"
HOLDER_STL = ARTIFACT_DIR / f"{STEM}.stl"
REAR_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_rear_dupont_render.png"
FRONT_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_front_pin_relief_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


P = {
    "body_width_mm": 40.0,
    "body_thickness_mm": 11.0,
    "pcb_pocket_depth_mm": 2.05,
    "pcb_thickness_mm": 1.6,
    "pin_x_mm": 10.2,
    "pin_pair_center_y_mm": -1.25,
    "pin_pitch_mm": 2.54,
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


def add_cylinder_x(name: str, radius: float, depth: float, location: tuple[float, float, float], material, vertices: int = 48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=(0, radians(90), 0))
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


def pin_y_positions() -> tuple[float, float]:
    half_pitch = P["pin_pitch_mm"] / 2.0
    y0 = P["pin_pair_center_y_mm"]
    return y0 - half_pitch, y0 + half_pitch


def add_proxy_parts(materials: dict[str, object]) -> None:
    half_t = P["body_thickness_mm"] / 2.0
    pcb_center_z = -half_t + P["pcb_pocket_depth_mm"] - P["pcb_thickness_mm"] / 2.0
    pin_z = pcb_center_z + 0.35
    y0 = P["pin_pair_center_y_mm"]
    width = P["body_width_mm"]

    add_cylinder_z("rear Lumileds PCB proxy with pin holes", 12.0, 1.6, (0, 0, pcb_center_z), materials["pcb"])
    add_cylinder_z("warm LED emitter marker", 2.5, 0.75, (0, 0, pcb_center_z + 1.2), materials["led"])
    add_box("right-angle 2P header plastic proxy", (4.4, 5.8, 2.8), (12.7, y0, pcb_center_z - 0.6), materials["header"])
    add_box("female Dupont 2P plug proxy", (12.0, 6.3, 5.2), (width / 2.0 + 5.8, y0, pcb_center_z - 0.25), materials["plug"])

    for index, y in enumerate(pin_y_positions(), start=1):
        add_cylinder_z(f"pin {index} front-side popup proxy", 0.33, 8.4, (P["pin_x_mm"], y, pcb_center_z + 2.2), materials["copper"])
        add_box(f"pin {index} right-angle leg proxy", (10.5, 0.65, 0.65), (17.1, y, pin_z), materials["copper"])
        wire_mat = materials["wire_red"] if index == 1 else materials["wire_black"]
        add_cylinder_x(f"Dupont wire {index} proxy", 0.45, 18.0, (width / 2.0 + 19.5, y, pin_z), wire_mat)


def setup_scene() -> dict[str, object]:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    materials = {
        "holder": make_material("translucent printed holder inspection material", (0.68, 0.66, 0.60, 0.42), roughness=0.62),
        "pcb": make_material("green Lumileds PCB proxy", (0.02, 0.36, 0.10, 0.82), roughness=0.5),
        "led": make_material("warm LED emitter marker", (1.0, 0.88, 0.50, 1.0), roughness=0.22),
        "header": make_material("black 2P right-angle header", (0.015, 0.015, 0.018, 1.0), roughness=0.44),
        "plug": make_material("translucent Dupont plug envelope", (0.03, 0.03, 0.04, 0.62), roughness=0.35),
        "copper": make_material("gold plated pins", (0.95, 0.62, 0.2, 1.0), roughness=0.28, metallic=0.65),
        "wire_red": make_material("red Dupont wire", (0.85, 0.04, 0.03, 1.0), roughness=0.5),
        "wire_black": make_material("black Dupont wire", (0.02, 0.02, 0.022, 1.0), roughness=0.5),
    }

    bpy.ops.import_mesh.stl(filepath=str(HOLDER_STL))
    holder = bpy.context.object
    holder.name = "printed_holder_with_2p_right_angle_clearance"
    holder.data.materials.append(materials["holder"])
    bpy.ops.object.shade_smooth()

    add_proxy_parts(materials)

    bpy.ops.object.light_add(type="AREA", location=(42, -56, -34))
    key = bpy.context.object
    key.name = "rear-side softbox"
    key.data.energy = 5400
    key.data.size = 58
    bpy.ops.object.light_add(type="AREA", location=(-38, 38, 48))
    fill = bpy.context.object
    fill.name = "front fill light"
    fill.data.energy = 1800
    fill.data.size = 48

    bpy.context.scene.render.engine = "BLENDER_EEVEE"
    bpy.context.scene.eevee.taa_render_samples = 64
    bpy.context.scene.eevee.use_gtao = True
    bpy.context.scene.eevee.gtao_distance = 4
    bpy.context.scene.eevee.gtao_factor = 0.65
    bpy.context.scene.world.color = (0.98, 0.985, 0.99)
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
    bpy.context.scene.view_settings.exposure = 1.05
    return materials


def render_view(path: Path, location: tuple[float, float, float], target: tuple[float, float, float], scale: float) -> None:
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    look_at(camera, target)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = scale
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    setup_scene()
    render_view(REAR_RENDER_PATH, (62, -72, -34), (7, -1, -2), 78)
    render_view(FRONT_RENDER_PATH, (38, -48, 86), (5, -1, 1.5), 70)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print(REAR_RENDER_PATH)
    print(FRONT_RENDER_PATH)


if __name__ == "__main__":
    main()
