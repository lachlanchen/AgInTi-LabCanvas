#!/usr/bin/env python3
"""Render printable saddle variants of the C-mount sensor holders."""

from __future__ import annotations

import json
import sys
from mathutils import Vector
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[2]
DESIGN_ROOT = ROOT / "cad/designs"

VARIANTS = {
    "gy302": "gy302_bh1750_cmount_light_sensor_holder_printable_saddle",
    "as7343": "as7343_cmount_spectral_module_holder_printable_saddle",
    "tsl25911": "tsl25911_cmount_intensity_sensor_holder_printable_saddle",
    "as7341": "as7341_cmount_sensor_holder_printable_saddle",
}


def args_after_blender() -> list[str]:
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return []


def selected_variants(args: list[str]) -> list[str]:
    if not args or args == ["all"]:
        return list(VARIANTS)
    for arg in args:
        if arg not in VARIANTS:
            valid = ", ".join(sorted(VARIANTS))
            raise SystemExit(f"Unknown variant {arg!r}. Valid: {valid}, all")
    return args


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.55, metallic: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Alpha"].default_value = color[3]
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if color[3] < 1.0:
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
    return mat


def look_at(obj, target: Vector) -> None:
    direction = target - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def import_stl(path: Path, name: str, mat):
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def object_bounds(objects) -> tuple[Vector, Vector]:
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, world.x)
            mins.y = min(mins.y, world.y)
            mins.z = min(mins.z, world.z)
            maxs.x = max(maxs.x, world.x)
            maxs.y = max(maxs.y, world.y)
            maxs.z = max(maxs.z, world.z)
    return mins, maxs


def add_floor(name: str, center: Vector, size: float, z: float, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(center.x, center.y, z - 0.06))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (size, size, 0.12)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def render(path: Path, cam, location: Vector, target: Vector, ortho_scale: float) -> None:
    cam.location = location
    look_at(cam, target)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def setup_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 64
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1300
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 1.15
    bpy.context.scene.world.color = (1, 1, 1)


def render_variant(key: str) -> None:
    stem = VARIANTS[key]
    design_dir = DESIGN_ROOT / stem
    artifact_dir = design_dir / "artifacts"
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    outputs = manifest["outputs"]

    setup_scene()
    mats = {
        "holder": material("matte warm gray printable holder", (0.62, 0.62, 0.56, 1.0), 0.68),
        "board": material("transparent blue board proxy", (0.02, 0.24, 0.82, 0.62), 0.45),
        "sensor": material("gold sensor datum", (1.0, 0.72, 0.08, 1.0), 0.35, 0.05),
        "accessory": material("cream connector/header proxy", (0.93, 0.88, 0.72, 0.70), 0.5),
        "axis": material("warm optical axis", (1.0, 0.74, 0.08, 0.72), 0.25),
        "floor": material("matte print bed plane", (0.82, 0.82, 0.78, 1.0), 0.7),
    }

    imported = []
    for out_key, label, mat_key in (
        ("holder_stl", "printable holder with integrated saddle", "holder"),
        ("board_proxy_stl", "board proxy", "board"),
        ("sensor_proxy_stl", "sensor datum proxy", "sensor"),
        ("accessory_proxy_stl", "connector/header clearance proxy", "accessory"),
        ("axis_proxy_stl", "optical axis proxy", "axis"),
    ):
        rel = outputs.get(out_key)
        if rel:
            imported.append(import_stl(ROOT / rel, label, mats[mat_key]))

    mins, maxs = object_bounds(imported)
    center = (mins + maxs) / 2.0
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z)
    floor_z = manifest["print_support_saddle"]["z_range_mm"][0]
    add_floor("print orientation floor plane", center, max(span * 1.45, 80.0), floor_z, mats["floor"])

    bpy.ops.object.light_add(type="AREA", location=(center.x - 30, center.y - 46, center.z + 55))
    key_light = bpy.context.object
    key_light.name = "large key softbox"
    key_light.data.energy = 2600
    key_light.data.size = 8.5
    bpy.ops.object.light_add(type="AREA", location=(center.x + 54, center.y + 34, center.z + 44))
    fill = bpy.context.object
    fill.name = "rear fill softbox"
    fill.data.energy = 1100
    fill.data.size = 12.0
    bpy.ops.object.camera_add(location=(0, 0, 0), rotation=(0, 0, 0))
    cam = bpy.context.object
    bpy.context.scene.camera = cam

    render_path = ROOT / outputs["render_png"]
    print_path = ROOT / outputs["print_orientation_render_png"]
    scale = max(span * 1.25, 68.0)
    render(render_path, cam, center + Vector((82, -96, 62)), center, scale)
    render(print_path, cam, center + Vector((84, -132, 34)), center, scale)
    bpy.ops.wm.save_as_mainfile(filepath=str(artifact_dir / f"{stem}.blend"))
    print(f"rendered {stem}: {render_path}")


def main() -> None:
    for key in selected_variants(args_after_blender()):
        render_variant(key)


if __name__ == "__main__":
    main()
