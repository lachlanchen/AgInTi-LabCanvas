#!/usr/bin/env python3
"""Render the OpenHI A 29.8 / C 29.6 mm female-receiver variant."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_a_c_bs_a29p8_c29p6_female_pivots"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
STL_PATH = ARTIFACT_DIR / f"{STEM}.stl"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / DESIGN_DIR.name
)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def make_material(name: str, rgba: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.diffuse_color = rgba
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Roughness"].default_value = 0.34
    shader.inputs["Metallic"].default_value = 0.08
    return material


def import_stl():
    try:
        bpy.ops.wm.stl_import(filepath=str(STL_PATH))
    except Exception:
        bpy.ops.import_mesh.stl(filepath=str(STL_PATH))
    obj = bpy.context.object
    obj.name = "OpenHI A+C+BS A 29.8 / C 29.6 mm female receivers"
    obj.data.materials.append(
        make_material("OpenHI warm metal", (0.24, 0.56, 0.66, 1.0))
    )
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def look_at(obj, target=(0.0, 0.0, 0.0)) -> None:
    obj.rotation_euler = (
        Vector(target) - obj.location
    ).to_track_quat("-Z", "Y").to_euler()


def setup_scene(resolution=(1800, 1400)):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.curvature_ridge_factor = 1.8
    scene.display.shading.curvature_valley_factor = 1.5
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.94, 0.96, 0.98)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"


def add_ground(z=-47.0) -> None:
    bpy.ops.mesh.primitive_plane_add(size=260.0, location=(0.0, 0.0, z))
    bpy.context.object.data.materials.append(
        make_material("ground", (0.15, 0.17, 0.20, 1.0))
    )


def add_camera(location, ortho_scale: float):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    look_at(camera)
    bpy.context.scene.camera = camera
    return camera


def center_from_manifest() -> Vector:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    minimum = manifest["validation"]["output"]["bbox"]["min"]
    maximum = manifest["validation"]["output"]["bbox"]["max"]
    return Vector(tuple((low + high) / 2.0 for low, high in zip(minimum, maximum)))


def bisect_camera_half(obj) -> None:
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    geometry = list(mesh.verts) + list(mesh.edges) + list(mesh.faces)
    bmesh.ops.bisect_plane(
        mesh,
        geom=geometry,
        plane_co=(0.0, 0.0, 0.0),
        plane_no=(0.0, 1.0, 0.0),
        clear_inner=True,
        clear_outer=False,
        dist=0.0001,
    )
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def render_full(center: Vector) -> None:
    clear_scene()
    holder = import_stl()
    holder.data = holder.data.copy()
    holder.location = -center
    add_ground()
    setup_scene()
    add_camera((105.0, -145.0, 100.0), 112.0)
    bpy.context.scene.render.filepath = str(ARTIFACT_DIR / f"{STEM}_render.png")
    bpy.ops.render.render(write_still=True)


def render_cutaway(center: Vector) -> None:
    clear_scene()
    holder = import_stl()
    holder.data = holder.data.copy()
    holder.location = -center
    bpy.context.view_layer.objects.active = holder
    holder.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    bisect_camera_half(holder)
    add_ground()
    setup_scene((1900, 1400))
    add_camera((92.0, -132.0, 82.0), 102.0)
    bpy.context.scene.render.filepath = str(
        ARTIFACT_DIR / f"{STEM}_thread_cutaway.png"
    )
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACT_DIR / f"{STEM}.blend"))


def main() -> None:
    bpy.context.preferences.filepaths.save_version = 0
    center = center_from_manifest()
    render_full(center)
    render_cutaway(center)
    shutil.copytree(
        DESIGN_DIR,
        NUTSTORE_DIR,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


if __name__ == "__main__":
    main()
