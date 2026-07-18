#!/usr/bin/env python3
"""Render the table-mount cradle, tube fit, section, and single print layout."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_4f_40mm_tube_cradle_50mm"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_stl(
    path: Path,
    name: str,
    color: tuple[float, float, float, float],
    smooth: bool = False,
) -> bpy.types.Object:
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=str(path))
    else:
        bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.color = color
    for polygon in obj.data.polygons:
        polygon.use_smooth = smooth
    return obj


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    minimum = Vector(
        (
            min(point.x for point in points),
            min(point.y for point in points),
            min(point.z for point in points),
        )
    )
    maximum = Vector(
        (
            max(point.x for point in points),
            max(point.y for point in points),
            max(point.z for point in points),
        )
    )
    return minimum, maximum, (minimum + maximum) * 0.5


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "OBJECT"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = True
    scene.world.color = (0.95, 0.97, 0.98)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1250
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 100


def add_floor(objects: list[bpy.types.Object]) -> None:
    minimum, maximum, center = bounds(objects)
    span = max(maximum.x - minimum.x, maximum.y - minimum.y, 60.0)
    bpy.ops.mesh.primitive_plane_add(
        size=span * 3.0,
        location=(center.x, center.y, minimum.z - 0.08),
    )
    floor = bpy.context.object
    floor.name = "print bed"
    floor.color = (0.80, 0.83, 0.86, 1.0)


def render(
    output: Path,
    objects: list[bpy.types.Object],
    camera_location: Vector,
    ortho_scale: float,
) -> None:
    _, _, center = bounds(objects)
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera, do_unlink=True)


def render_single() -> None:
    clear_scene()
    holder = import_stl(
        ARTIFACT_DIR / f"{STEM}_holder.stl",
        "40.2 mm circular-seat table-mount cradle",
        (0.08, 0.50, 0.76, 1.0),
    )
    objects = [holder]
    add_floor(objects)
    configure_scene()
    _, _, center = bounds(objects)
    render(
        ARTIFACT_DIR / f"{STEM}_single_render.png",
        objects,
        center + Vector((82.0, -104.0, 70.0)),
        86.0,
    )


def render_print_layout() -> None:
    clear_scene()
    layout = import_stl(
        ARTIFACT_DIR / f"{STEM}_single_with_anti_warp_ears.stl",
        "single direct-print cradle with four anti-warp ears",
        (0.08, 0.50, 0.76, 1.0),
    )
    objects = [layout]
    add_floor(objects)
    configure_scene()
    _, _, center = bounds(objects)
    render(
        ARTIFACT_DIR / f"{STEM}_single_with_anti_warp_ears_render.png",
        objects,
        center + Vector((105.0, -135.0, 110.0)),
        128.0,
    )
    render(
        ARTIFACT_DIR / f"{STEM}_single_with_anti_warp_ears_top_render.png",
        objects,
        center + Vector((0.0, 0.0, 180.0)),
        190.0,
    )


def render_mounting_pattern() -> None:
    clear_scene()
    holder = import_stl(
        ARTIFACT_DIR / f"{STEM}_holder.stl",
        "two-wing 50 mm mounting pattern",
        (0.08, 0.50, 0.76, 1.0),
    )
    objects = [holder]
    add_floor(objects)
    configure_scene()
    _, _, center = bounds(objects)
    render(
        ARTIFACT_DIR / f"{STEM}_mounting_pattern_top_render.png",
        objects,
        center + Vector((0.0, 0.0, 120.0)),
        115.0,
    )


def render_fit() -> None:
    clear_scene()
    holder = import_stl(
        ARTIFACT_DIR / f"{STEM}_holder.stl",
        "printed cradle",
        (0.08, 0.50, 0.76, 1.0),
    )
    tube = import_stl(
        ARTIFACT_DIR / f"{STEM}_tube_proxy_od40.stl",
        "40 mm OpenHI tube proxy",
        (0.94, 0.40, 0.07, 1.0),
        smooth=True,
    )
    objects = [holder, tube]
    add_floor(objects)
    configure_scene()
    _, _, center = bounds(objects)
    render(
        ARTIFACT_DIR / f"{STEM}_fit_check_render.png",
        objects,
        center + Vector((92.0, -116.0, 78.0)),
        96.0,
    )
    render(
        ARTIFACT_DIR / f"{STEM}_cross_section_fit_render.png",
        objects,
        center + Vector((120.0, 0.0, 1.0)),
        76.0,
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACT_DIR / f"{STEM}.blend"))


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    render_single()
    render_mounting_pattern()
    render_print_layout()
    render_fit()


if __name__ == "__main__":
    main()
