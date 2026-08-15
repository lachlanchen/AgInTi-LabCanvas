#!/usr/bin/env python3
"""Render the checked OpenHI Lens C 29.8 mm right female-receiver variant."""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_lens_c_holder_right_female_29p8_pivot"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
STL_PATH = ARTIFACT_DIR / f"{STEM}.stl"


def make_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Alpha"].default_value = color[3]
    shader.inputs["Roughness"].default_value = roughness
    material.diffuse_color = color
    if color[3] < 1.0:
        material.blend_method = "BLEND"
        if hasattr(material, "use_screen_refraction"):
            material.use_screen_refraction = True
    return material


def import_stl(path: Path):
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=str(path))
    else:
        bpy.ops.import_mesh.stl(filepath=str(path))
    return bpy.context.object


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_settings() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1400
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "WORLD"
    shading.curvature_ridge_factor = 1.7
    shading.curvature_valley_factor = 1.4
    shading.show_specular_highlight = True
    shading.show_object_outline = True
    shading.object_outline_color = (0.025, 0.035, 0.05)
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.90, 0.92, 0.94)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0


def add_lights() -> None:
    for location, energy, size in (
        ((75, -95, 100), 1200, 70),
        ((-70, -20, 45), 850, 55),
        ((25, 80, 15), 700, 45),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
    for location, energy in (
        ((70, -80, 45), 900),
        ((-55, -35, 15), 520),
    ):
        bpy.ops.object.light_add(type="POINT", location=location)
        point = bpy.context.object
        point.data.energy = energy
        point.data.shadow_soft_size = 18.0


def add_floor(bottom_z: float) -> None:
    floor_material = make_material(
        "neutral floor",
        (0.72, 0.76, 0.80, 1.0),
        0.82,
    )
    bpy.ops.mesh.primitive_plane_add(size=340, location=(0, 0, bottom_z - 0.8))
    floor = bpy.context.object
    floor.name = "neutral floor"
    floor.data.materials.append(floor_material)


def add_optical_axis(center: Vector, cutaway: bool) -> None:
    axis_material = make_material(
        "optical axis",
        (0.98, 0.52, 0.04, 0.90),
        0.30,
    )
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64,
        radius=0.34,
        depth=64.0,
        location=(315.0 - center.x, 210.0 - center.y, 600.0 - center.z),
    )
    axis = bpy.context.object
    axis.name = "optical axis"
    axis.rotation_euler[1] = math.radians(90.0)
    axis.data.materials.append(axis_material)
    if cutaway:
        axis.hide_render = False


def add_receiver_envelope(manifest: dict, center: Vector) -> None:
    receiver_material = make_material(
        "30.6 mm groove envelope",
        (0.04, 0.65, 0.34, 0.19),
        0.42,
    )
    receiver = manifest["receiver"]
    x0, x1 = receiver["thread_x_range_mm"]
    groove = manifest["thread"]["target_female_groove_mm"]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=128,
        radius=groove / 2.0,
        depth=x1 - x0,
        location=((x0 + x1) / 2.0 - center.x, 210.0 - center.y, 600.0 - center.z),
    )
    envelope = bpy.context.object
    envelope.name = "target female groove envelope"
    envelope.rotation_euler[1] = math.radians(90.0)
    envelope.data.materials.append(receiver_material)


def load_holder(manifest: dict, *, cutaway: bool):
    center = Vector(manifest["validation"]["output"]["bbox"]["center"])
    holder = import_stl(STL_PATH)
    holder.name = "OpenHI Lens C holder, 29.8 mm right female pivot"
    holder.data.materials.append(
        make_material(
            "cutaway graphite polymer" if cutaway else "warm gray polymer",
            (0.56, 0.62, 0.68, 1.0) if cutaway else (0.33, 0.58, 0.78, 1.0),
            0.46,
        )
    )
    if cutaway:
        bpy.context.view_layer.objects.active = holder
        holder.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.bisect(
            plane_co=(0.0, 210.0, 0.0),
            plane_no=(0.0, 1.0, 0.0),
            clear_outer=True,
            use_fill=False,
        )
        bpy.ops.object.mode_set(mode="OBJECT")
    holder.location = -center
    add_optical_axis(center, cutaway)
    return center


def setup_scene(*, cutaway: bool) -> dict:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    load_holder(manifest, cutaway=cutaway)
    add_lights()
    bpy.ops.object.camera_add(location=(105, -135, 92))
    bpy.context.scene.camera = bpy.context.object
    render_settings()
    return manifest


def render(
    output: Path,
    camera_location: tuple[float, float, float],
    target: tuple[float, float, float],
    ortho_scale: float,
) -> None:
    camera = bpy.context.scene.camera
    camera.location = camera_location
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    look_at(camera, target)
    bpy.context.scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    setup_scene(cutaway=False)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    add_receiver_envelope(
        manifest,
        Vector(manifest["validation"]["output"]["bbox"]["center"]),
    )
    render(
        ARTIFACT_DIR / f"{STEM}_render.png",
        (88, -112, 76),
        (0, 0, 0),
        80,
    )
    setup_scene(cutaway=False)
    render(
        ARTIFACT_DIR / f"{STEM}_thread_detail.png",
        (94, -38, 28),
        (17, 0, 0),
        45,
    )
    setup_scene(cutaway=True)
    render(
        ARTIFACT_DIR / f"{STEM}_thread_cutaway.png",
        (76, -112, 30),
        (8, -3, 0),
        68,
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACT_DIR / f"{STEM}.blend"))


if __name__ == "__main__":
    main()
