#!/usr/bin/env python3
"""Render the unchanged apparatus with physically scaled studio illumination."""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(ROOT / "cad/tools"))
from blender_camera_fit import fit_camera_to_objects


def principled(name, color, metal=0, rough=0.35, transmission=0, emission=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["IOR"].default_value = 1.46
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*color, 1)
        bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def setup(samples):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.04
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 6
    scene.cycles.transparent_max_bounces = 8
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 6
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.1
    scene.world = bpy.data.worlds.new("Soft studio ambient")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12
    for name, pos, power, size in (
        ("Large soft key", (0.5, -0.8, 1.5), 24, 0.8),
        ("Cool fill", (-0.65, -0.4, 0.75), 10, 0.65),
        ("Rear edge", (0.3, 0.75, 1.3), 24, 0.5),
    ):
        bpy.ops.object.light_add(type="AREA", location=pos)
        obj = bpy.context.object
        obj.name = name
        obj.data.energy = power
        obj.data.shape = "DISK"
        obj.data.size = size
        obj.rotation_euler = (Vector((0.05, 0, 0.45)) - obj.location).to_track_quat("-Z", "Y").to_euler()
    mats = {
        "polymer": principled("Graphite polymer", (0.045, 0.058, 0.075), rough=0.4),
        "polymer_mid": principled("Satin graphite housing", (0.075, 0.095, 0.12), metal=0.2, rough=0.3),
        "metal": principled("Satin aluminium", (0.57, 0.64, 0.7), metal=0.75, rough=0.27),
        "camera": principled("Frame detector housing", (0.065, 0.13, 0.18), metal=0.45, rough=0.28),
        "event_camera": principled("Event detector housing", (0.12, 0.075, 0.055), metal=0.45, rough=0.28),
        "sensor": principled("Spectrometer package", (0.62, 0.65, 0.66), metal=0.7, rough=0.24),
        "pcb": principled("PCB green", (0.018, 0.19, 0.075), rough=0.35),
        "glass": principled("Clear optical glass", (0.87, 0.97, 0.98), rough=0.06, transmission=0.94),
        "lens": principled("Optical lens", (0.84, 0.95, 0.98), rough=0.04, transmission=0.96),
        "beam_splitter": principled("Beam splitter", (0.84, 0.95, 0.98), rough=0.05, transmission=0.96),
        "polarizer": principled("Neutral polarizing film", (0.12, 0.16, 0.17), rough=0.12, transmission=0.45),
        "sample": principled("Specimen reference", (0.15, 0.56, 0.46), rough=0.2, transmission=0.3),
        "bulb": principled("Tungsten bulb reference", (0.97, 0.62, 0.15), rough=0.12, transmission=0.6, emission=0.15),
    }
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.0003))
    ground = bpy.context.object
    ground.name = "Studio shadow catcher"
    ground.is_shadow_catcher = True
    ground.data.materials.append(principled("White shadow surface", (1, 1, 1), rough=0.9))
    scene.use_nodes = False
    return mats, ground


def load_parts(entry, mats):
    objects = {}
    for row in entry["render_components"]:
        bpy.ops.wm.stl_import(filepath=str(ROOT / row["source_mesh"]))
        obj = bpy.context.object
        obj.name = row["name"]
        obj.is_shadow_catcher = False
        obj.is_holdout = False
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.transform(Matrix.Scale(0.001, 4))
        obj.data.update()
        category = "bulb" if obj.name == "tungsten_bulb" else row["category"]
        obj.data.materials.clear()
        obj.data.materials.append(mats.get(category, mats["polymer_mid"]))
        for face in obj.data.polygons:
            face.material_index = 0
            face.use_smooth = True
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(35)
        if obj.name.endswith("camera_body") or obj.name in {"dock", "lamp_holder", "LCD_lower_holder", "LCD_upper_holder", "sample_holder_and_cap"}:
            bevel = obj.modifiers.new("Render-only edge highlights", "BEVEL")
            bevel.width = 0.00015
            bevel.segments = 2
            bevel.limit_method = "ANGLE"
        normal = obj.modifiers.new("Area weighted normals", "WEIGHTED_NORMAL")
        normal.keep_sharp = True
        objects[obj.name] = obj
    return objects


def fit(objects, resolution, direction):
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    camera, bounds = fit_camera_to_objects(objects, direction=direction)
    # The shared mm-scale helper has a 1-unit minimum. Fit metre-scale details tightly.
    factor = max((bounds["xmax"] - bounds["xmin"]) / 0.84, (bounds["ymax"] - bounds["ymin"]) / 0.84)
    camera.data.ortho_scale *= factor
    bpy.context.view_layer.update()
    uv = [world_to_camera_view(scene, camera, obj.matrix_world @ Vector(p)) for obj in objects for p in obj.bound_box]
    bounds = {"xmin": min(p.x for p in uv), "xmax": max(p.x for p in uv), "ymin": min(p.y for p in uv), "ymax": max(p.y for p in uv)}
    if not (0.079 <= bounds["xmin"] < bounds["xmax"] <= 0.921 and 0.079 <= bounds["ymin"] < bounds["ymax"] <= 0.921):
        raise RuntimeError(f"Clipped apparatus: {bounds}")
    return camera, bounds


def anchors(objects, camera):
    names = {"Frame camera": "frame_camera_body", "Event camera": "event_camera_body",
             "Spectrometer": "c12880_board", "Upper GT090101": "GT090101_upper", "Upper LCD": "LCD_upper_holder",
             "Specimen": "sample_volume", "Lower LCD": "LCD_lower_holder", "Lower GT090101": "GT090101_lower", "Lamp": "lamp_holder",
             "Microscope": "openhi_microscope", "Relay 1": "primary_4f_beam_splitter_reference", "Relay 2": "secondary_4f_beam_splitter_reference"}
    result = {}
    for label, name in names.items():
        if name in objects:
            center = sum((objects[name].matrix_world @ Vector(p) for p in objects[name].bound_box), Vector()) / 8
            point = world_to_camera_view(bpy.context.scene, camera, center)
            result[label] = list(point)
    return result


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--variant", choices=("single_4f", "dual_4f", "dual_4f_vertical"))
    parser.add_argument("--view", choices=("overview", "detectors", "lower"))
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args(argv)
    latest = json.loads((DESIGN / "artifacts/publication_latest.json").read_text())
    run = ROOT / latest["run_dir"]
    data = json.loads((run / "manifest.json").read_text())
    out = run / ("previews" if args.preview else "renders")
    out.mkdir(exist_ok=True)
    records = []
    for variant, entry in data["variants"].items():
        if args.variant and variant != args.variant:
            continue
        mats, ground = setup(20 if args.preview else data["render_settings"]["samples"])
        objects = load_parts(entry, mats)
        lower = set(entry["lower_detail_components"])
        upper = {name for name in objects if name.startswith(("primary_4f_", "secondary_4f_", "frame_camera_", "event_camera_", "c12880_", "vertical_cascade"))}
        views = [(variant + "_overview", set(objects), (2400, 3400) if variant == "dual_4f" else (1800, 3800), (1.35, -3.5, 0.9), "overview"),
                 (variant + "_detectors", upper, (2600, 2000) if variant != "dual_4f_vertical" else (1900, 2700), (1.25, -3.3, 1.2), "detectors")]
        if variant == "single_4f":
            views += [("lower_stack_detail", lower, (2500, 2500), (-1.8, -3.8, 0.65), "lower"),
                      ("lower_stack_opposite", lower, (2500, 2500), (1.8, 3.8, 0.65), "lower")]
        for name, names, resolution, direction, kind in views:
            if args.view and kind != args.view:
                continue
            for key, obj in objects.items():
                obj.hide_render = key not in names
            ground.hide_render = True
            selected = [obj for key, obj in objects.items() if key in names]
            if args.preview:
                scale = 950 / max(resolution)
                resolution = tuple(int(v * scale) for v in resolution)
            cam, bounds = fit(selected, resolution, direction)
            scene = bpy.context.scene
            scene.render.filepath = str(out / (name + ".png"))
            if not args.metadata_only:
                bpy.ops.render.render(write_still=True)
                # Flatten after the display transform, preserving antialiasing and soft shadows.
                subprocess.run([str(ROOT / "cad/.conda/cad-python/bin/python"), str(DESIGN / "publication_figure.py"),
                                "--flatten", scene.render.filepath], check=True)
            records.append({"name": name, "file": name + ".png", "variant": variant,
                            "projected_bounds": bounds, "visible_components": sorted(names), "anchors": anchors(objects, cam),
                            "resolution": list(resolution), "engine": scene.render.engine, "device": scene.cycles.device})
            bpy.data.objects.remove(cam, do_unlink=True)
        if not args.preview and not args.view and not args.metadata_only:
            for obj in objects.values():
                obj.hide_render = False
            ground.hide_render = True
            fit(list(objects.values()), (2400, 3400), (1.35, -3.5, 0.9))
            bpy.ops.wm.save_as_mainfile(filepath=str(run / f"{variant}_publication_scene.blend"))
    file = out / "camera_validation.json"
    if file.exists():
        old = {row["name"]: row for row in json.loads(file.read_text())}
        old.update({row["name"]: row for row in records})
        records = list(old.values())
    file.write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
