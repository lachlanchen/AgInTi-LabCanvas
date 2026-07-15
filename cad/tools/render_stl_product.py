#!/usr/bin/env python3
"""Render a complete STL print layout with a stable isometric camera."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--color", type=float, nargs=3, default=(0.18, 0.58, 0.66))
    return parser.parse_args(args)


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    minimum = Vector((min(point.x for point in corners), min(point.y for point in corners), min(point.z for point in corners)))
    maximum = Vector((max(point.x for point in corners), max(point.y for point in corners), max(point.z for point in corners)))
    return minimum, maximum


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    bpy.ops.wm.stl_import(filepath=str(args.input))
    model = bpy.context.object
    model.name = args.input.stem
    material = bpy.data.materials.new("part material")
    material.diffuse_color = (*args.color, 1.0)
    model.data.materials.append(material)

    minimum, maximum = world_bounds(model)
    center = (minimum + maximum) * 0.5
    dimensions = maximum - minimum
    maximum_dimension = max(dimensions.x, dimensions.y, dimensions.z, 1.0)

    bpy.ops.mesh.primitive_plane_add(size=maximum_dimension * 4.0, location=(center.x, center.y, minimum.z - 0.08))
    floor = bpy.context.object
    floor.name = "print bed"
    floor_material = bpy.data.materials.new("print bed material")
    floor_material.diffuse_color = (0.82, 0.84, 0.86, 1.0)
    floor.data.materials.append(floor_material)

    camera_offset = Vector((1.35, -1.55, 1.10)) * maximum_dimension
    bpy.ops.object.camera_add(location=center + camera_offset)
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = maximum_dimension * 1.62
    track = camera.constraints.new(type="TRACK_TO")
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=center)
    track.target = bpy.context.object
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.world.color = (0.96, 0.97, 0.98)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1300
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(args.output)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
