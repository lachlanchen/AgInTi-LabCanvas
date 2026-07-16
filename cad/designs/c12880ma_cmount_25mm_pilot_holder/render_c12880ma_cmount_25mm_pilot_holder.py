#!/usr/bin/env python3
"""Render assembled and exploded C12880MA holder views with Blender."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "c12880ma_cmount_25mm_pilot_holder"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_stl(path: Path, name: str, color: tuple[float, float, float, float]):
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=str(path))
    else:
        bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.color = color
    return obj


def scene_bounds(objects) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    center = sum(points, Vector()) / len(points)
    size = Vector(
        (
            max(point.x for point in points) - min(point.x for point in points),
            max(point.y for point in points) - min(point.y for point in points),
            max(point.z for point in points) - min(point.z for point in points),
        )
    )
    return center, size


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "OBJECT"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = True
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.94, 0.96, 0.98)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"


def render(path: Path, objects, camera_location: tuple[float, float, float], scale: float) -> None:
    center, _ = scene_bounds(objects)
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = scale
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera, do_unlink=True)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    clear_scene()
    body = import_stl(
        ARTIFACT_DIR / f"{STEM}_body.stl",
        "25 mm pilot optical body",
        (0.08, 0.48, 0.78, 1.0),
    )
    sensor = import_stl(
        ARTIFACT_DIR / f"{STEM}_sensor_proxy.stl",
        "C12880MA official-envelope proxy",
        (0.08, 0.10, 0.13, 1.0),
    )
    retainer = import_stl(
        ARTIFACT_DIR / f"{STEM}_retainer.stl",
        "rear lead-window retainer",
        (0.96, 0.39, 0.08, 1.0),
    )
    objects = [body, sensor, retainer]
    configure_scene()

    center, _ = scene_bounds(objects)
    render(
        ARTIFACT_DIR / f"{STEM}_assembled_render.png",
        objects,
        (center.x - 44.0, center.y - 48.0, center.z + 35.0),
        56.0,
    )
    render(
        ARTIFACT_DIR / f"{STEM}_side_alignment_render.png",
        objects,
        (center.x, center.y - 75.0, center.z + 1.0),
        46.0,
    )

    sensor.location.x += 8.0
    retainer.location.x += 20.0
    exploded_center, _ = scene_bounds(objects)
    render(
        ARTIFACT_DIR / f"{STEM}_exploded_render.png",
        objects,
        (exploded_center.x - 52.0, exploded_center.y - 54.0, exploded_center.z + 38.0),
        68.0,
    )
    sensor.location.x -= 8.0
    retainer.location.x -= 20.0

    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACT_DIR / f"{STEM}.blend"))
    print(ARTIFACT_DIR / f"{STEM}_assembled_render.png")
    print(ARTIFACT_DIR / f"{STEM}_exploded_render.png")


if __name__ == "__main__":
    main()
