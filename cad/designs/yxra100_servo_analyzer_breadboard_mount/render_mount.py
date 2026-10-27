#!/usr/bin/env python3
"""Render the complete fixture and each direct-print model without cropping."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

DESIGN = Path(__file__).resolve().parent
ART = DESIGN / "artifacts"
OUT = ART / "renders"


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    return mat


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.background_type = "WORLD"
    scene.world = bpy.data.worlds.new("White review background")
    scene.world.color = (1, 1, 1)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    return scene


def mesh(path, name, color):
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material(name, color))
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(35)
    normal = obj.modifiers.new("Area weighted planar normals", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    return obj


def fit_and_render(objects, name, direction=(1.5, -2.0, 1.2), resolution=(1800, 1600)):
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    points = [obj.matrix_world @ Vector(p) for obj in objects for p in obj.bound_box]
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center = (lo + hi) / 2
    span = max((hi - lo).length, 1)
    bpy.ops.object.camera_add(location=center + Vector(direction).normalized() * span * 3)
    cam = bpy.context.object
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.clip_end = span * 10
    rotation = cam.rotation_euler.to_matrix().transposed()
    projected = [rotation @ (p - center) for p in points]
    xmin, xmax = min(p.x for p in projected), max(p.x for p in projected)
    ymin, ymax = min(p.y for p in projected), max(p.y for p in projected)
    local_center = Vector(((xmin + xmax) / 2, (ymin + ymax) / 2, 0))
    cam.location += rotation.transposed() @ local_center
    aspect = resolution[0] / resolution[1]
    cam.data.ortho_scale = max(ymax - ymin, (xmax - xmin) / aspect) * 1.18
    scene.camera = cam
    bpy.context.view_layer.update()
    from bpy_extras.object_utils import world_to_camera_view
    # Blender's AUTO sensor fit changes the meaning of ortho_scale with image
    # aspect. Fit from actual projected bounds instead of assuming a convention.
    for _ in range(4):
        uv = [world_to_camera_view(scene, cam, p) for p in points]
        width = max(p.x for p in uv) - min(p.x for p in uv)
        height = max(p.y for p in uv) - min(p.y for p in uv)
        factor = max(width / 0.84, height / 0.84, 1)
        if factor <= 1.00001:
            break
        cam.data.ortho_scale *= factor * 1.001
        bpy.context.view_layer.update()
    uv = [world_to_camera_view(scene, cam, p) for p in points]
    bounds = {"xmin": min(p.x for p in uv), "xmax": max(p.x for p in uv),
              "ymin": min(p.y for p in uv), "ymax": max(p.y for p in uv)}
    if not (0.03 < bounds["xmin"] < bounds["xmax"] < 0.97 and 0.03 < bounds["ymin"] < bounds["ymax"] < 0.97):
        raise RuntimeError(f"Camera cropping: {name}: {bounds}")
    scene.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return {"file": f"{name}.png", "projected_bounds": bounds, "object_count": len(objects)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ART / "manifest.json").read_text())
    reset()
    objects = {}
    for row in manifest["render_components"]:
        objects[row["name"]] = mesh(ART / row["mesh"], row["name"], row["color"])
    evidence = [fit_and_render(list(objects.values()), "complete_rotary_analyzer_setup", resolution=(1800, 2200))]
    microscope = objects["openhi_microscope_relocated"]
    microscope.hide_render = True
    upper_names = {"openhi_microscope_relocated", "primary_openhi_4f", "microscope_to_4f_adapter"}
    upper_names.update(name for name in objects if name.startswith(("frame_camera_", "c12880_")))
    for name in upper_names:
        objects[name].hide_render = True
    detail = [obj for name, obj in objects.items() if name not in upper_names]
    evidence.append(fit_and_render(detail, "stage_stand_and_sample_clearance", direction=(1.4, -2, 1.5)))
    evidence.append(fit_and_render(detail, "sample_access_opposite_view", direction=(-1.5, -2, 1.0)))
    for name, obj in objects.items():
        obj.hide_render = name not in {"breadboard_foot", "gusseted_L_support", "YXRA100_servo_vendor", "rotating_analyzer_adapter", "GT090101_analyzer"}
    exploded = []
    for name, delta in (("YXRA100_servo_vendor", 45), ("rotating_analyzer_adapter", 70), ("GT090101_analyzer", 95)):
        objects[name].location.z += delta
    bpy.context.view_layer.update()
    exploded = [obj for obj in objects.values() if not obj.hide_render]
    evidence.append(fit_and_render(exploded, "exploded_rotary_mount", direction=(1.5, -2, 1.5), resolution=(1800, 1900)))
    reset()
    for path in sorted(ART.glob("PRINT_THIS_*.stl")):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        obj = mesh(path, path.stem, (0.20, 0.43, 0.51))
        evidence.append(fit_and_render([obj], path.stem + "_render", direction=(1.3, -1.7, 1.4)))
    reset()
    layout = []
    for name, x, y in (("yxra100_L_support_on_back_with_ears", 0, 0),
                       ("yxra100_breadboard_foot_with_ears", 155, 0),
                       ("yxra100_full_GT090101_rotating_adapter", 160, 145)):
        obj = mesh(ART / f"PRINT_THIS_{name}.stl", name, (0.20, 0.43, 0.51))
        obj.location.x, obj.location.y = x, y
        layout.append(obj)
    bpy.context.view_layer.update()
    evidence.append(fit_and_render(layout, "separate_direct_print_parts_overview", resolution=(2000, 1600)))
    (OUT / "camera_validation.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
