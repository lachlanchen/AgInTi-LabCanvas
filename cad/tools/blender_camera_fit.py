"""Orthographic framing with a verified margin around complete CAD objects."""

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def fit_camera_to_objects(objects, *, direction=(1.5, -2.0, 1.2), margin=0.08):
    if not objects or not 0 < margin < 0.4:
        raise ValueError("Objects and a safe margin are required")
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(p) for obj in objects for p in obj.bound_box]
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center = (lo + hi) / 2
    span = max((hi - lo).length, 1)
    bpy.ops.object.camera_add(location=center + Vector(direction).normalized() * span * 3)
    camera = bpy.context.object
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.clip_end = span * 10
    rotation = camera.rotation_euler.to_matrix().transposed()
    projected = [rotation @ (p - center) for p in points]
    xmin, xmax = min(p.x for p in projected), max(p.x for p in projected)
    ymin, ymax = min(p.y for p in projected), max(p.y for p in projected)
    camera.location += rotation.transposed() @ Vector(((xmin + xmax) / 2, (ymin + ymax) / 2, 0))
    camera.data.ortho_scale = max(xmax - xmin, ymax - ymin, 1) * 1.2
    scene = bpy.context.scene
    scene.camera = camera
    for _ in range(5):
        bpy.context.view_layer.update()
        uv = [world_to_camera_view(scene, camera, p) for p in points]
        width = max(p.x for p in uv) - min(p.x for p in uv)
        height = max(p.y for p in uv) - min(p.y for p in uv)
        factor = max(width / (1 - 2 * margin), height / (1 - 2 * margin), 1)
        if factor <= 1.00001:
            break
        camera.data.ortho_scale *= factor * 1.001
    bpy.context.view_layer.update()
    uv = [world_to_camera_view(scene, camera, p) for p in points]
    bounds = {"xmin": min(p.x for p in uv), "xmax": max(p.x for p in uv),
              "ymin": min(p.y for p in uv), "ymax": max(p.y for p in uv)}
    tolerance = 0.001
    if not (margin - tolerance <= bounds["xmin"] < bounds["xmax"] <= 1 - margin + tolerance
            and margin - tolerance <= bounds["ymin"] < bounds["ymax"] <= 1 - margin + tolerance):
        raise RuntimeError(f"CAD render would crop or violate margin: {bounds}")
    return camera, bounds
