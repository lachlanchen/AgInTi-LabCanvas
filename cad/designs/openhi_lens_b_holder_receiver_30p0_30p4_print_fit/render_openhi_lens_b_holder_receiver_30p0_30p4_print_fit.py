#!/usr/bin/env python3
"""Render the OpenHI Lens B holder 30.0/30.4 mm receiver variant."""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_lens_b_holder_receiver_30p0_30p4_print_fit"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
STL_PATH = ARTIFACT_DIR / f"{STEM}.stl"
RENDER_PATH = ARTIFACT_DIR / f"{STEM}_render.png"
THREAD_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_thread_detail_render.png"
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
    return mat


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_settings() -> None:
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 80
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1400
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 1.05
    bpy.context.scene.world.color = (1, 1, 1)


def add_axis_and_receiver_overlays(manifest: dict, center: Vector, cutaway: bool = False) -> None:
    params = manifest["params"]
    mat_axis = material("gold optical axis", (1.0, 0.72, 0.08, 0.92), 0.28)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64,
        radius=0.42 if not cutaway else 0.34,
        depth=92.0,
        location=(params["axis_x_mm"] - center.x, params["axis_y_mm"] - center.y, 622.6 - center.z),
    )
    axis = bpy.context.object
    axis.name = "lens optical axis"
    axis.data.materials.append(mat_axis)

    if not cutaway:
        mat_receiver = material("transparent green 30.4 receiver groove envelope", (0.0, 0.65, 0.28, 0.24), 0.42)
        z_center = params["thread_z0_mm"] + params["thread_length_mm"] / 2.0
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=128,
            radius=params["female_thread_cutter_max_diameter_mm"] / 2.0,
            depth=params["thread_length_mm"],
            location=(params["axis_x_mm"] - center.x, params["axis_y_mm"] - center.y, z_center - center.z),
        )
        receiver = bpy.context.object
        receiver.name = "30.4 mm receiver groove envelope"
        receiver.data.materials.append(mat_receiver)


def import_holder(center: Vector, cutaway: bool = False):
    mat_holder = material(
        "cutaway warm gray Lens B 30.0/30.4 receiver" if cutaway else "warm gray Lens B 30.0/30.4 receiver",
        (0.68, 0.67, 0.61, 1.0),
        0.64,
    )
    bpy.ops.import_mesh.stl(filepath=str(STL_PATH))
    holder = bpy.context.object
    holder.name = "OpenHI Lens B holder 30.0/30.4 receiver variant"
    holder.data.materials.append(mat_holder)
    holder.location = -center
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
    return holder


def setup_scene(cutaway: bool = False) -> dict:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    center = Vector(manifest["source_geometry"]["bbox"]["center"])
    import_holder(center, cutaway=cutaway)
    add_axis_and_receiver_overlays(manifest, center, cutaway=cutaway)

    bpy.ops.object.light_add(type="AREA", location=(30, -60, 55))
    key = bpy.context.object
    key.name = "large key softbox"
    key.data.energy = 2700
    key.data.size = 8.0
    bpy.ops.object.light_add(type="AREA", location=(-55, 42, 35))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 1000
    fill.data.size = 10.0
    bpy.ops.object.camera_add(location=(120, -150, 92))
    bpy.context.scene.camera = bpy.context.object
    render_settings()
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
    setup_scene()
    render(RENDER_PATH, (120, -150, 92), (0, 0, 0), 140)
    render(THREAD_RENDER_PATH, (24, -30, 90), (0, 0, 36), 46)
    setup_scene(cutaway=True)
    render(CUTAWAY_RENDER_PATH, (82, -96, 64), (0, -4, 8), 102)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
