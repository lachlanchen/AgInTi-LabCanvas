#!/usr/bin/env python3
"""Blender renders for the EVK 5 holder move: overview, inside view, top view, side section.

Run:  blender --background --python <this file> -- [--design-dir DIR]
Uses the grouped STL meshes written by the build script (artifacts/render_meshes).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

COLORS = {
    "holder_moved": (0.95, 0.45, 0.10, 1.0),
    "holder_original": (0.95, 0.45, 0.10, 0.25),
    "sensor_plate": (0.15, 0.55, 0.25, 1.0),
    "grating": (0.20, 0.35, 0.85, 1.0),
    "walls": (0.80, 0.82, 0.85, 0.35),
    "lower_shelf": (0.70, 0.72, 0.75, 1.0),
    "upper_shelf": (0.70, 0.72, 0.75, 1.0),
    "stage": (0.45, 0.45, 0.48, 1.0),
    "rest": (0.60, 0.60, 0.62, 1.0),
    "axis": (1.0, 0.90, 0.10, 1.0),
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--design-dir", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--samples", type=int, default=16)
    return ap.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def material(name: str, rgba: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.55
        if rgba[3] < 1.0:
            bsdf.inputs["Alpha"].default_value = rgba[3]
            mat.blend_method = "BLEND"
            if hasattr(mat, "shadow_method"):
                mat.shadow_method = "HASHED"
    if name == "axis" and bsdf:
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = 3.0
    return mat


def import_group(path: Path, name: str) -> bpy.types.Object | None:
    if not path.exists():
        return None
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material(name, COLORS.get(name, (0.6, 0.6, 0.6, 1.0))))
    obj.color = COLORS.get(name, (0.6, 0.6, 0.6, 1.0))
    for poly in obj.data.polygons:
        poly.use_smooth = False
    return obj


def bounds(objs: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def add_camera(location: Vector, target: Vector, ortho_scale: float | None = None, name: str = "cam") -> bpy.types.Object:
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = name
    if ortho_scale:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    else:
        cam.data.lens = 40
    direction = target - location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = 10000
    bpy.context.scene.camera = cam
    return cam


def setup_render(engine: str, samples: int) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1300
    scene.render.film_transparent = False
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.color = (1.0, 1.0, 1.0)
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
        bg.inputs[1].default_value = 1.0
    try:
        scene.render.engine = engine
    except Exception:
        scene.render.engine = "BLENDER_WORKBENCH"
    if scene.render.engine == "BLENDER_WORKBENCH":
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "OBJECT"
        sh.show_cavity = True
        sh.show_shadows = True
        sh.show_xray = False
        sh.background_type = "VIEWPORT"
        sh.background_color = (1.0, 1.0, 1.0)
        sh.cavity_type = "SCREEN"
        sh.curvature_ridge_factor = 0.6
        sh.curvature_valley_factor = 0.6
    else:
        try:
            scene.eevee.taa_render_samples = samples
        except Exception:
            pass


def render(path: Path) -> None:
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def add_label_lights() -> None:
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 1000))
    sun = bpy.context.object
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(35), math.radians(-25), math.radians(20))


def main() -> None:
    args = parse_args()
    meshes = args.design_dir / "artifacts" / "render_meshes"
    out = args.design_dir / "artifacts" / "renders"
    out.mkdir(parents=True, exist_ok=True)
    clear_scene()
    setup_render("BLENDER_WORKBENCH", args.samples)
    add_label_lights()
    objs = {n: import_group(meshes / f"{n}.stl", n) for n in COLORS}
    objs = {k: v for k, v in objs.items() if v is not None}
    solid = [o for k, o in objs.items() if k not in ("holder_original",)]
    lo, hi = bounds(list(objs.values()))
    centre = (lo + hi) / 2
    size = max(hi - lo)

    # 1. overview: whole box, front open side visible, original (ghost) and moved holder
    for k, o in objs.items():
        o.hide_render = False
    objs["walls"].hide_render = False
    cam = add_camera(centre + Vector((-1.15, -1.55, 0.95)) * size, centre, name="overview")
    render(out / "01_overview_before_after.png")
    bpy.data.objects.remove(cam)

    # 2. inside view: hide walls/lid and stage, look from the open front, slightly above
    objs["walls"].hide_render = True
    if "stage" in objs:
        objs["stage"].hide_render = True
    objs["holder_original"].hide_render = True
    objs["upper_shelf"].hide_render = True
    inner = [objs[k] for k in ("holder_moved", "sensor_plate", "grating") if k in objs]
    lo2, hi2 = bounds(inner)
    c2 = (lo2 + hi2) / 2
    s2 = max(hi2 - lo2)
    cam = add_camera(c2 + Vector((-0.75, -1.35, 0.55)) * s2, c2, name="inside")
    render(out / "02_inside_holder_on_sensor_board.png")
    bpy.data.objects.remove(cam)

    # 3. top view (orthographic) through the grating window: hide grating and upper shelf? keep grating semi
    objs["grating"].hide_render = True
    objs["lower_shelf"].hide_render = True
    lo3, hi3 = bounds([objs["holder_moved"], objs["sensor_plate"]])
    c3 = (lo3 + hi3) / 2
    cam = add_camera(Vector((c3.x, c3.y, c3.z + 600)), Vector((c3.x, c3.y, c3.z)), ortho_scale=max(hi3.x - lo3.x, hi3.y - lo3.y) * 1.25, name="top")
    cam.rotation_euler = (0.0, 0.0, 0.0)
    render(out / "03_top_view_alignment.png")
    bpy.data.objects.remove(cam)
    objs["grating"].hide_render = False
    objs["lower_shelf"].hide_render = False
    objs["upper_shelf"].hide_render = False

    # 4. side elevation (orthographic, from -Y) showing stack: plate, holder, gap, grating
    lo4, hi4 = bounds([objs["holder_moved"], objs["sensor_plate"], objs["grating"]])
    c4 = (lo4 + hi4) / 2
    cam = add_camera(Vector((c4.x, c4.y - 800, c4.z)), c4, ortho_scale=max(hi4.x - lo4.x, hi4.z - lo4.z) * 1.35, name="side")
    render(out / "04_side_elevation_light_path.png")
    bpy.data.objects.remove(cam)

    # 5. holder group alone (moved), iso
    for k, o in objs.items():
        o.hide_render = k not in ("holder_moved", "sensor_plate")
    lo5, hi5 = bounds([objs["holder_moved"]])
    c5 = (lo5 + hi5) / 2
    s5 = max(hi5 - lo5)
    cam = add_camera(c5 + Vector((1.3, -1.6, 1.1)) * s5, c5, name="holder")
    render(out / "05_holder_group_on_plate_detail.png")
    bpy.data.objects.remove(cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))


if __name__ == "__main__":
    main()
