#!/usr/bin/env python3
"""Render the exact-regenerated OpenHI Lens B holder."""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_lens_b_holder_shapr_exact_regen"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
STL_PATH = ARTIFACT_DIR / f"{STEM}.stl"
CUTAWAY_STL_PATH = ARTIFACT_DIR / f"{STEM}_inspection_cutaway.stl"
RENDER_PATH = ARTIFACT_DIR / f"{STEM}_render.png"
THREAD_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_thread_detail_render.png"
CUTAWAY_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_inspection_cutaway_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.55, metallic: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Alpha"].default_value = color[3]
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if color[3] < 1.0:
        mat.blend_method = "BLEND"
    return mat


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_scene() -> dict:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    center = Vector(manifest["reference_geometry"]["bbox"]["center"])
    mat_holder = material("warm gray exact OpenHI Lens B holder", (0.64, 0.63, 0.58, 1.0), 0.64)
    mat_axis = material("gold optical axis markers", (1.0, 0.72, 0.08, 0.9), 0.28)
    mat_thread = material("transparent blue measured lens-thread zone", (0.1, 0.35, 1.0, 0.28), 0.48)

    bpy.ops.import_mesh.stl(filepath=str(STL_PATH))
    holder = bpy.context.object
    holder.name = "OpenHI Lens B holder exact B-rep regeneration"
    holder.data.materials.append(mat_holder)
    holder.location = -center

    # Lens-thread zone reference, centered from measured face-scan values.
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=15.1, depth=8.55, location=(254.633 - center.x, 210.0 - center.y, 656.625 - center.z))
    thread_zone = bpy.context.object
    thread_zone.name = "measured 30.2 mm lens-thread zone envelope"
    thread_zone.data.materials.append(mat_thread)

    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.45, depth=92.0, location=(254.633 - center.x, 210.0 - center.y, 622.6 - center.z))
    axis = bpy.context.object
    axis.name = "lens optical axis"
    axis.data.materials.append(mat_axis)

    bpy.ops.object.light_add(type="AREA", location=(30, -60, 55))
    key = bpy.context.object
    key.name = "large key softbox"
    key.data.energy = 2600
    key.data.size = 8.0
    bpy.ops.object.light_add(type="AREA", location=(-55, 42, 35))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 1000
    fill.data.size = 10.0
    bpy.ops.object.camera_add(location=(120, -150, 92))
    cam = bpy.context.object
    look_at(cam, (0, 0, 0))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 140
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 80
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1400
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 1.05
    bpy.context.scene.world.color = (1, 1, 1)
    return manifest


def setup_cutaway_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    center = Vector(manifest["reference_geometry"]["bbox"]["center"])
    mat_holder = material("cutaway warm gray exact B-rep", (0.68, 0.67, 0.62, 1.0), 0.62)
    mat_axis = material("gold optical axis marker", (1.0, 0.72, 0.08, 0.95), 0.28)

    bpy.ops.import_mesh.stl(filepath=str(CUTAWAY_STL_PATH))
    cutaway = bpy.context.object
    cutaway.name = "OpenHI Lens B holder exact B-rep half cutaway"
    cutaway.data.materials.append(mat_holder)
    cutaway.location = -center

    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.35, depth=92.0, location=(254.633 - center.x, 210.0 - center.y, 622.6 - center.z))
    axis = bpy.context.object
    axis.name = "lens optical axis"
    axis.data.materials.append(mat_axis)

    bpy.ops.object.light_add(type="AREA", location=(26, -46, 58))
    key = bpy.context.object
    key.name = "cutaway key softbox"
    key.data.energy = 3000
    key.data.size = 8.0
    bpy.ops.object.light_add(type="AREA", location=(-40, 30, 20))
    fill = bpy.context.object
    fill.name = "cutaway fill"
    fill.data.energy = 1100
    fill.data.size = 10.0
    bpy.ops.object.camera_add(location=(82, -96, 64))
    cam = bpy.context.object
    look_at(cam, (0, -4, 8))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 102
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 80
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1400
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 1.05
    bpy.context.scene.world.color = (1, 1, 1)


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> None:
    cam = bpy.context.scene.camera
    cam.location = camera_location
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    setup_scene()
    render(RENDER_PATH, (120, -150, 92), (0, 0, 0), 140)
    render(THREAD_RENDER_PATH, (24, -30, 90), (0, 0, 36), 46)
    setup_cutaway_scene()
    render(CUTAWAY_RENDER_PATH, (82, -96, 64), (0, -4, 8), 102)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
