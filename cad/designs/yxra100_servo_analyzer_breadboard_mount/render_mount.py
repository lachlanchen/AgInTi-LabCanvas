#!/usr/bin/env python3
"""Render the complete fixture and each direct-print model without cropping."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

DESIGN = Path(__file__).resolve().parent
ART = DESIGN / "artifacts"
OUT = ART / "renders"
sys.path.insert(0, str(DESIGN.parents[1] / "tools"))
from blender_camera_fit import fit_camera_to_objects


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
    cam, bounds = fit_camera_to_objects(objects, direction=direction)
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
    yoke_names = {name for name in objects if name.startswith(("motor_yoke_", "bridge_M3_"))}
    if yoke_names:
        selected = yoke_names | {"YXRA100_servo_vendor", "breadboard_foot", "gusseted_L_support"}
        for name, obj in objects.items():
            obj.hide_render = name not in selected
        evidence.append(fit_and_render([objects[name] for name in selected], "square_y_motor_support_detail", direction=(1.6, -2, 1.4)))
        objects["motor_yoke_stand_foot"].hide_render = True
        table_yoke = mesh(ART / "motor_yoke_direct_table.stl", "motor_yoke_direct_table", (0.20, 0.43, 0.51))
        table_view = [objects[name] for name in selected if name != "motor_yoke_stand_foot"] + [table_yoke]
        evidence.append(fit_and_render(table_view, "square_y_direct_table_variant", direction=(1.6, -2, 1.4)))
        bpy.data.objects.remove(table_yoke, do_unlink=True)
        for name, obj in objects.items():
            obj.hide_render = name not in yoke_names
        lifted = {name for name in yoke_names if name == "motor_yoke_top_bridge" or name.startswith("bridge_M3_screw_")}
        for name in lifted:
            objects[name].location.z += 20
        bpy.context.view_layer.update()
        evidence.append(fit_and_render([objects[name] for name in yoke_names], "M3_top_bridge_exploded", direction=(1.7, -2.2, 1.3)))
        for name in lifted:
            objects[name].location.z -= 20
    for name, obj in objects.items():
        obj.hide_render = name not in ({"breadboard_foot", "gusseted_L_support", "YXRA100_servo_vendor", "rotating_analyzer_adapter", "GT090101_analyzer"} | yoke_names)
    exploded = []
    for name, delta in (("YXRA100_servo_vendor", 45), ("rotating_analyzer_adapter", 70), ("GT090101_analyzer", 95)):
        objects[name].location.z += delta
    bpy.context.view_layer.update()
    exploded = [obj for obj in objects.values() if not obj.hide_render]
    evidence.append(fit_and_render(exploded, "exploded_rotary_mount", direction=(1.5, -2, 1.5), resolution=(1800, 1900)))
    reset()
    print_stems = [row["stem"] for row in manifest["print_validation"].values()]
    for stem in print_stems:
        path = ART / f"{stem}.stl"
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        obj = mesh(path, path.stem, (0.20, 0.43, 0.51))
        evidence.append(fit_and_render([obj], path.stem + "_render", direction=(1.3, -1.7, 1.4)))
    reset()
    layout = []
    placements = [("yxra100_L_support_on_back_with_ears", 0, 0),
                  ("yxra100_breadboard_foot_with_ears", 155, 0),
                  ("yxra100_full_GT090101_rotating_adapter", 160, -150)]
    if yoke_names:
        placements += [("yxra100_motor_yoke_stand_foot", 315, 0),
                       ("yxra100_motor_yoke_direct_table", 470, 0),
                       ("yxra100_motor_yoke_M3_top_bridge", 315, -150)]
    for name, x, y in placements:
        obj = mesh(ART / f"PRINT_THIS_{name}.stl", name, (0.20, 0.43, 0.51))
        obj.location.x, obj.location.y = x, y
        layout.append(obj)
    bpy.context.view_layer.update()
    evidence.append(fit_and_render(layout, "separate_direct_print_parts_overview", resolution=(2000, 1600)))
    (OUT / "camera_validation.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
