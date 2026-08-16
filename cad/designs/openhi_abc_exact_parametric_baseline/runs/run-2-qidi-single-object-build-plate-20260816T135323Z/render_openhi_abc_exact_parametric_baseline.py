#!/usr/bin/env python3
"""Render full-view evidence for the exact OpenHI A/B/C baseline."""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
STEMS = {
    "A": "OpenHI_A_exact_current_geometry",
    "B": "OpenHI_B_exact_current_geometry",
    "C": "OpenHI_C_exact_current_geometry",
}
COLORS = {
    "A": (0.94, 0.42, 0.10, 1.0),
    "B": (0.05, 0.55, 0.50, 1.0),
    "C": (0.12, 0.37, 0.78, 1.0),
}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)


def make_material(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Metallic"].default_value = 0.10
    return material


def import_stl(path: Path, name: str, material) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=str(path))
    else:
        bpy.ops.import_mesh.stl(filepath=str(path))
    created = [obj for obj in bpy.context.scene.objects if obj not in before]
    if not created:
        raise RuntimeError(f"Blender did not import {path}")
    obj = created[0]
    obj.name = name
    obj.data.materials.append(material)
    return obj


def world_bbox(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return minimum, maximum


def center_object(obj: bpy.types.Object, target: Vector = Vector((0.0, 0.0, 0.0))) -> Vector:
    minimum, maximum = world_bbox(obj)
    center = (minimum + maximum) / 2.0
    obj.location += target - center
    return maximum - minimum


def place_on_build_plate(obj: bpy.types.Object, target_x: float) -> Vector:
    minimum, maximum = world_bbox(obj)
    center = (minimum + maximum) / 2.0
    obj.location += Vector((target_x - center.x, -center.y, -minimum.z))
    minimum, maximum = world_bbox(obj)
    if abs(minimum.z) > 1e-4:
        raise RuntimeError(f"{obj.name} is not on the build plate: {minimum.z}")
    return maximum - minimum


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(scale: float, target: Vector = Vector((0.0, 0.0, 0.0))) -> None:
    bpy.ops.object.camera_add(location=(scale * 1.45, -scale * 1.75, scale * 1.25))
    camera = bpy.context.object
    camera.name = "full geometry camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = scale * 1.55
    look_at(camera, target)
    bpy.context.scene.camera = camera


def add_lighting(scale: float) -> None:
    bpy.ops.object.light_add(type="AREA", location=(scale * 0.9, -scale * 1.2, scale * 1.7))
    key = bpy.context.object
    key.name = "large key softbox"
    key.data.energy = 1800.0
    key.data.shape = "DISK"
    key.data.size = scale * 0.9
    bpy.ops.object.light_add(type="AREA", location=(-scale * 1.1, -scale * 0.2, scale * 0.6))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 900.0
    fill.data.size = scale * 0.75
    bpy.ops.object.light_add(type="AREA", location=(0.0, scale * 1.4, scale * 1.2))
    rim = bpy.context.object
    rim.name = "rim light"
    rim.data.energy = 1100.0
    rim.data.size = scale * 0.65
    bpy.ops.object.light_add(
        type="SUN",
        location=(0.0, 0.0, scale * 2.0),
        rotation=(math.radians(24.0), math.radians(-18.0), math.radians(-28.0)),
    )
    sun = bpy.context.object
    sun.name = "clean daylight"
    sun.data.energy = 1.15
    sun.data.angle = math.radians(18.0)


def add_floor(z: float, size: float) -> None:
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0.0, 0.0, z))
    floor = bpy.context.object
    floor.name = "neutral evidence floor"
    floor.data.materials.append(make_material("floor", (0.91, 0.92, 0.93, 1.0)))


def configure_render(path: Path) -> None:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1300
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(path)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.10
    scene.view_settings.gamma = 1.0
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.965, 0.97, 0.975, 1.0)
    background.inputs["Strength"].default_value = 0.35
    scene.camera.data.lens = 52.0
    bpy.ops.render.render(write_still=True)


def render_single(key: str) -> None:
    clear_scene()
    stem = STEMS[key]
    material = make_material(f"OpenHI {key}", COLORS[key])
    obj = import_stl(ARTIFACT_DIR / f"{stem}.stl", f"OpenHI {key} exact body", material)
    size = center_object(obj)
    scale = max(size) * 1.02
    minimum, _ = world_bbox(obj)
    add_floor(minimum.z - max(size) * 0.035, max(size) * 4.2)
    add_camera(scale)
    add_lighting(scale)
    configure_render(ARTIFACT_DIR / f"{stem}_render.png")


def add_label(text: str, location: tuple[float, float, float], scale: float) -> None:
    bpy.ops.object.text_add(location=location, rotation=(math.radians(75.0), 0.0, 0.0))
    label = bpy.context.object
    label.name = f"label {text}"
    label.data.body = text
    label.data.align_x = "CENTER"
    label.data.size = scale
    label.data.extrude = scale * 0.025
    label.data.materials.append(make_material(f"label {text}", (0.08, 0.09, 0.11, 1.0)))


def render_overview() -> None:
    clear_scene()
    positions = {"A": -67.0, "B": 0.0, "C": 70.0}
    min_z = 0.0
    for key in ("A", "B", "C"):
        stem = STEMS[key]
        obj = import_stl(
            ARTIFACT_DIR / f"{stem}.stl",
            f"OpenHI {key} exact body",
            make_material(f"OpenHI {key}", COLORS[key]),
        )
        size = center_object(obj, Vector((positions[key], 0.0, 0.0)))
        minimum, _ = world_bbox(obj)
        min_z = min(min_z, minimum.z)
        add_label(key, (positions[key], -35.0, min_z + size.z * 0.05), 8.0)
    add_floor(min_z - 2.0, 360.0)
    bpy.ops.object.camera_add(location=(175.0, -235.0, 155.0))
    camera = bpy.context.object
    camera.name = "A B C overview camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 225.0
    look_at(camera, Vector((0.0, 0.0, 0.0)))
    bpy.context.scene.camera = camera
    add_lighting(105.0)
    configure_render(ARTIFACT_DIR / "OpenHI_ABC_exact_current_geometry_overview.png")
    bpy.ops.wm.save_as_mainfile(
        filepath=str(ARTIFACT_DIR / "OpenHI_ABC_exact_current_geometry.blend")
    )


def render_print_ready_overview() -> None:
    clear_scene()
    positions = {"A": -62.0, "B": 0.0, "C": 62.0}
    for key in ("A", "B", "C"):
        stem = STEMS[key]
        obj = import_stl(
            ARTIFACT_DIR / f"PRINT_THIS_{stem}.stl",
            f"PRINT THIS OpenHI {key}",
            make_material(f"print OpenHI {key}", COLORS[key]),
        )
        size = place_on_build_plate(obj, positions[key])
        add_label(key, (positions[key], -31.0, 0.5), 7.0)
    add_floor(-0.8, 320.0)
    bpy.ops.object.camera_add(location=(160.0, -225.0, 135.0))
    camera = bpy.context.object
    camera.name = "print-ready overview camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 205.0
    look_at(camera, Vector((0.0, 0.0, 24.0)))
    bpy.context.scene.camera = camera
    add_lighting(100.0)
    configure_render(ARTIFACT_DIR / "OpenHI_ABC_PRINT_THIS_build_plate_overview.png")


def main() -> None:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("run the baseline builder before rendering")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not manifest["validation"]["all_pass"]:
        raise RuntimeError("refusing to render an unvalidated baseline")
    for key in ("A", "B", "C"):
        render_single(key)
    render_overview()
    render_print_ready_overview()
    print(
        json.dumps(
            {
                "renders": [
                    str(ARTIFACT_DIR / f"{STEMS[key]}_render.png")
                    for key in ("A", "B", "C")
                ]
                + [
                    str(ARTIFACT_DIR / "OpenHI_ABC_exact_current_geometry_overview.png"),
                    str(ARTIFACT_DIR / "OpenHI_ABC_PRINT_THIS_build_plate_overview.png"),
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
