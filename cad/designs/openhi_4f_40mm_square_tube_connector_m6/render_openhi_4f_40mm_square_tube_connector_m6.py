#!/usr/bin/env python3
"""Render the square 40 mm tube connector, stop section, and screw grid."""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_4f_40mm_square_tube_connector_m6"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name: str, color: tuple[float, float, float, float], metallic: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.28 if metallic else 0.38
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Alpha"].default_value = color[3]
    mat.blend_method = "BLEND" if color[3] < 1.0 else "OPAQUE"
    return mat


def import_stl(path: Path, name: str, mat: bpy.types.Material) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    try:
        bpy.ops.wm.stl_import(filepath=str(path))
    except Exception:
        bpy.ops.import_mesh.stl(filepath=str(path))
    created = [obj for obj in bpy.context.scene.objects if obj not in before]
    if not created:
        raise RuntimeError(f"Failed to import {path}")
    obj = created[0]
    obj.name = name
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def add_ground(size: float = 150.0) -> None:
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0.0, 0.0, -0.08))
    ground = bpy.context.object
    ground.data.materials.append(material("ground", (0.18, 0.21, 0.26, 1.0)))


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_scene(
    camera_location: tuple[float, float, float],
    target: tuple[float, float, float],
    *,
    resolution: tuple[int, int] = (1400, 1100),
) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.curvature_ridge_factor = 1.7
    scene.display.shading.curvature_valley_factor = 1.4
    scene.display.shading.show_specular_highlight = True
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.92, 0.94, 0.97)

    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.data.lens = 58
    look_at(camera, target)
    scene.camera = camera

    for location, energy, size in (
        ((70.0, -80.0, 105.0), 1300.0, 55.0),
        ((-75.0, -35.0, 70.0), 1000.0, 45.0),
        ((20.0, 85.0, 95.0), 1150.0, 50.0),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        look_at(light, target)


def render(path: Path) -> None:
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def connector_render(materials: dict[str, bpy.types.Material]) -> None:
    clear_scene()
    import_stl(
        ARTIFACT_DIR / f"{STEM}_threaded_connector.stl",
        "threaded square connector",
        materials["connector"],
    )
    add_ground()
    setup_scene((88.0, -98.0, 82.0), (0.0, 0.0, 31.0))
    render(ARTIFACT_DIR / f"{STEM}_connector_render.png")


def fit_render(materials: dict[str, bpy.types.Material]) -> None:
    clear_scene()
    import_stl(
        ARTIFACT_DIR / f"{STEM}_threaded_connector.stl",
        "connector",
        materials["connector"],
    )
    import_stl(
        ARTIFACT_DIR / f"{STEM}_assembled_set_screws.stl",
        "eight set screws",
        materials["screw"],
    )
    import_stl(
        ARTIFACT_DIR / f"{STEM}_lower_tube_proxy.stl",
        "lower tube",
        materials["tube"],
    )
    import_stl(
        ARTIFACT_DIR / f"{STEM}_upper_tube_proxy.stl",
        "upper tube",
        materials["tube"],
    )
    add_ground()
    setup_scene((112.0, -126.0, 92.0), (0.0, 0.0, 31.0))
    render(ARTIFACT_DIR / f"{STEM}_fit_check_render.png")


def section_render(materials: dict[str, bpy.types.Material]) -> None:
    clear_scene()
    import_stl(
        ARTIFACT_DIR / f"{STEM}_half_section.stl",
        "connector half section",
        materials["section"],
    )
    add_ground()
    setup_scene((-88.0, -108.0, 70.0), (0.0, 0.0, 31.0))
    render(ARTIFACT_DIR / f"{STEM}_center_stop_section_render.png")


def screw_grid_render(materials: dict[str, bpy.types.Material]) -> None:
    clear_scene()
    import_stl(
        ARTIFACT_DIR / f"{STEM}_8x_set_screw_grid.stl",
        "eight screw print grid",
        materials["screw"],
    )
    add_ground(100.0)
    setup_scene((62.0, -72.0, 55.0), (0.0, 0.0, 7.0), resolution=(1400, 900))
    render(ARTIFACT_DIR / f"{STEM}_8x_set_screw_grid_render.png")


def main() -> None:
    materials = {
        "connector": material("connector blue", (0.08, 0.34, 0.74, 1.0)),
        "section": material("section cyan", (0.05, 0.54, 0.62, 1.0)),
        "screw": material("screw graphite", (0.25, 0.29, 0.35, 1.0), metallic=0.35),
        "tube": material("tube amber", (1.0, 0.32, 0.04, 0.40), metallic=0.05),
    }
    connector_render(materials)
    fit_render(materials)
    section_render(materials)
    screw_grid_render(materials)


if __name__ == "__main__":
    main()
