#!/usr/bin/env python3
"""Render the exact-regenerated OpenHI Lens C holder."""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_lens_c_holder_shapr_exact_regen"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
STL_PATH = ARTIFACT_DIR / f"{STEM}.stl"
CUTAWAY_STL_PATH = ARTIFACT_DIR / f"{STEM}_inspection_cutaway.stl"
RENDER_PATH = ARTIFACT_DIR / f"{STEM}_render.png"
RECEIVER_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_receiver_detail_render.png"
CUTAWAY_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_inspection_cutaway_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Alpha"].default_value = color[3]
    bsdf.inputs["Roughness"].default_value = roughness
    if color[3] < 1.0:
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
    return mat


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_x_cylinder(name: str, radius: float, depth: float, location: tuple[float, float, float], mat) -> None:
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler[1] = math.radians(90)
    obj.data.materials.append(mat)


def base_render_settings() -> None:
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 80
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1400
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 1.05
    bpy.context.scene.world.color = (1, 1, 1)


def setup_scene(stl_path: Path, cutaway: bool = False) -> dict:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    center = Vector(manifest["reference_geometry"]["bbox"]["center"])
    mat_holder = material("warm gray exact OpenHI Lens C holder", (0.66, 0.65, 0.60, 1.0), 0.64)
    mat_axis = material("gold optical axis", (1.0, 0.72, 0.08, 0.9), 0.28)
    mat_thread = material("transparent blue receiver thread envelope", (0.1, 0.35, 1.0, 0.24), 0.48)

    bpy.ops.import_mesh.stl(filepath=str(stl_path))
    holder = bpy.context.object
    holder.name = "OpenHI Lens C holder exact B-rep regeneration"
    holder.data.materials.append(mat_holder)
    holder.location = -center

    add_x_cylinder("optical axis", 0.35, 62.0, (0, 0, 0), mat_axis)
    if not cutaway:
        add_x_cylinder("left Thread BS envelope", 15.3, 6.3, (292.75 - center.x, 0, 0), mat_thread)
        add_x_cylinder("right receiver thread envelope", 15.1, 8.6, (331.6 - center.x, 0, 0), mat_thread)

    bpy.ops.object.light_add(type="AREA", location=(45, -60, 65))
    key = bpy.context.object
    key.name = "large key softbox"
    key.data.energy = 2800
    key.data.size = 8.5
    bpy.ops.object.light_add(type="AREA", location=(-45, 35, 30))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 1000
    fill.data.size = 11.0
    bpy.ops.object.camera_add(location=(88, -116, 70))
    bpy.context.scene.camera = bpy.context.object
    base_render_settings()
    return manifest


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> None:
    cam = bpy.context.scene.camera
    cam.location = camera_location
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    setup_scene(STL_PATH)
    render(RENDER_PATH, (88, -116, 70), (0, 0, 0), 92)
    render(RECEIVER_RENDER_PATH, (86, -26, 20), (18, 0, 0), 44)
    setup_scene(CUTAWAY_STL_PATH, cutaway=True)
    render(CUTAWAY_RENDER_PATH, (86, -92, 52), (0, -4, 0), 76)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
