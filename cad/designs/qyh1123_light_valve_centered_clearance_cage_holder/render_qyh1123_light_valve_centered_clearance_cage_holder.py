#!/usr/bin/env python3
"""Render the QYH1123 light-valve centered clearance cage holder."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "qyh1123_light_valve_centered_clearance_cage_holder"
HOLDER_STL = ARTIFACT_DIR / f"{STEM}.stl"
RENDER_PATH = ARTIFACT_DIR / f"{STEM}_render.png"
TOP_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_top_alignment_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


P = {
    "body_width": 42.0,
    "body_height": 42.0,
    "body_thickness": 8.0,
    "rod_pitch": 30.0,
    "rod_diameter": 5.9,
    "valve_width": 18.0,
    "valve_height": 20.0,
    "valve_thickness": 2.0,
    "valve_center_x": 0.0,
    "valve_center_y": 0.0,
    "active_width": 15.0,
    "active_height": 15.0,
    "light_window_width": 13.0,
    "light_window_height": 13.0,
    "pin_pitch": 2.54,
    "pin_width": 0.70,
    "pin_length": 8.0,
    "pin_thickness": 0.50,
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


def setup_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    materials = {
        "holder": make_material("matte graphite printed holder", (0.28, 0.28, 0.26, 1.0), roughness=0.66),
        "valve": make_material("transparent LCD valve body", (0.26, 0.78, 0.92, 0.48), roughness=0.22),
        "active": make_material("transparent 15 mm visible area reference", (0.65, 0.95, 1.0, 0.28), roughness=0.2),
        "window": make_material("warm 13 mm light pass reference", (1.0, 0.78, 0.25, 0.74), roughness=0.2),
        "rod": make_material("blue cage rod alignment proxies", (0.15, 0.45, 0.9, 0.46), roughness=0.34),
        "pin": make_material("gold metal pin tails", (0.95, 0.58, 0.16, 0.95), roughness=0.22, metallic=0.65),
    }

    bpy.ops.import_mesh.stl(filepath=str(HOLDER_STL))
    holder = bpy.context.object
    holder.name = "qyh1123_clean_printable_holder_from_stl"
    holder.data.materials.clear()
    holder.data.materials.append(materials["holder"])

    front_z = P["body_thickness"] / 2.0
    valve_center_z = front_z - 2.4 + P["valve_thickness"] / 2.0 + 0.18
    add_box(
        "QYH1123 18 x 20 x 2 mm valve proxy",
        (P["valve_width"], P["valve_height"], P["valve_thickness"]),
        (P["valve_center_x"], P["valve_center_y"], valve_center_z),
        materials["valve"],
    )
    add_box(
        "15 x 15 mm active area centered on cage origin",
        (P["active_width"], P["active_height"], 0.22),
        (0, 0, valve_center_z + P["valve_thickness"] / 2.0 + 0.12),
        materials["active"],
    )
    add_box(
        "13 x 13 mm through-window after 1 mm terrace",
        (P["light_window_width"], P["light_window_height"], 0.24),
        (0, 0, valve_center_z + P["valve_thickness"] / 2.0 + 0.26),
        materials["window"],
    )

    pin_y = P["valve_center_y"] - P["valve_height"] / 2.0 - P["pin_length"] / 2.0
    pin_z = valve_center_z - P["valve_thickness"] / 2.0 + P["pin_thickness"] / 2.0
    for index, x in enumerate((P["valve_center_x"] - P["pin_pitch"] / 2.0, P["valve_center_x"] + P["pin_pitch"] / 2.0), start=1):
        add_box(
            f"QYH1123 pin tail {index}",
            (P["pin_width"], P["pin_length"], P["pin_thickness"]),
            (x, pin_y, pin_z),
            materials["pin"],
        )

    rod_half = P["rod_pitch"] / 2.0
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            add_cylinder_z(
                "30 mm cage rod alignment",
                P["rod_diameter"] / 2.0,
                P["body_thickness"] + 5.0,
                (x, y, 0),
                materials["rod"],
            )

    bpy.ops.object.light_add(type="AREA", location=(0, -36, 46))
    light = bpy.context.object
    light.name = "large softbox"
    light.data.energy = 1250
    light.data.size = 5.8
    bpy.ops.object.light_add(type="AREA", location=(-34, 28, 34))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 430
    fill.data.size = 8.5

    bpy.ops.object.camera_add(location=(40, -50, 34), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (0, 0, 0.6))
    cam.data.lens = 58
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 56
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 0
    bpy.context.scene.view_settings.gamma = 1
    bpy.context.scene.world.color = (1, 1, 1)


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
    render(RENDER_PATH, (40, -50, 34), (0, 0, 0.6), 58)
    render(TOP_RENDER_PATH, (0, 0, 70), (0, 0, 0.6), 58, ortho=True, ortho_scale=48)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
