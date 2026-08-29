#!/usr/bin/env python3
"""Render an assembled same-lens OpenHI 4f design with Blender."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name: str, color: tuple[float, float, float, float], metallic: float = 0.0, roughness: float = 0.42):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if color[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = color[3]
        bsdf.inputs["Transmission Weight"].default_value = 0.25
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
    return mat


def look_at(camera, target: Vector):
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_axis_curve(name: str, points: list[tuple[float, float, float]], mat):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.45
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for item, point in zip(spline.points, points):
        item.co = (*point, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    design_dir = args.design_dir.resolve()
    artifact_dir = design_dir / "artifacts"
    manifest = json.loads((artifact_dir / "manifest.json").read_text())
    render_dir = artifact_dir / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    body_mats = {
        "A": material("A", (0.28, 0.55, 0.82, 1.0), metallic=0.18),
        "A_C_BS": material("A_C_BS", (0.48, 0.54, 0.62, 1.0), metallic=0.24),
        "B": material("B", (0.25, 0.68, 0.48, 1.0), metallic=0.18),
        "C": material("C", (0.86, 0.46, 0.24, 1.0), metallic=0.18),
        "Lens_B_holder": material("Lens_B_holder", (0.61, 0.42, 0.78, 1.0), metallic=0.16),
        "Lens_C_holder": material("Lens_C_holder", (0.28, 0.66, 0.78, 1.0), metallic=0.16),
    }
    glass = material("Lens glass", (0.18, 0.75, 0.90, 0.42), roughness=0.12)
    bs_glass = material("Beam splitter", (0.78, 0.90, 1.0, 0.30), roughness=0.08)
    axis_mat = material("Optical axes", (0.95, 0.20, 0.08, 1.0), roughness=0.25)

    for path in sorted((artifact_dir / "assembly_components").glob("*.stl")):
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = bpy.context.object
        obj.name = path.stem
        if path.stem.startswith("lens_"):
            obj.data.materials.append(glass)
        elif path.stem == "beam_splitter_reference":
            obj.data.materials.append(bs_glass)
        else:
            obj.data.materials.append(body_mats[path.stem])
        for polygon in obj.data.polygons:
            polygon.use_smooth = path.stem.startswith("lens_")

    f = float(manifest["optical_layout"]["catalog_efl_mm"])
    add_axis_curve("A-B optical axis", [(255, 210, 600 - f - 18), (255, 210, 600 + f + 18)], axis_mat)
    add_axis_curve("C optical axis", [(255, 210, 600), (255 + f + 32, 210, 600)], axis_mat)

    bpy.ops.mesh.primitive_plane_add(size=320, location=(255, 210, 475))
    floor = bpy.context.object
    floor.data.materials.append(material("Floor", (0.055, 0.065, 0.075, 1.0), roughness=0.72))

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("OpenHI World")
        bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.12, 0.15, 0.19, 1.0)
    background.inputs["Strength"].default_value = 0.65
    for location, energy, size in [((140, 90, 800), 1900, 110), ((440, 330, 760), 1450, 95), ((180, 350, 540), 1050, 85)]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        look_at(light, Vector((255, 210, 600)))

    bpy.ops.object.camera_add(location=(470, 20, 790))
    camera = bpy.context.object
    look_at(camera, Vector((285, 210, 605)))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 270
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.filepath = str(render_dir / "openhi_4f_assembly.png")
    bpy.ops.render.render(write_still=True)

    camera.location = (440, -20, 625)
    look_at(camera, Vector((285, 210, 600)))
    camera.data.ortho_scale = 235
    scene.render.filepath = str(render_dir / "openhi_4f_optical_axis.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
