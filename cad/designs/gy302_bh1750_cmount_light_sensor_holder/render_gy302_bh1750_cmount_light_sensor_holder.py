#!/usr/bin/env python3
"""Render the GY-302 BH1750 C-mount light sensor holder."""

from __future__ import annotations

import json
from math import radians
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "gy302_bh1750_cmount_light_sensor_holder"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
HOLDER_STL = ARTIFACT_DIR / f"{STEM}.stl"
BOARD_STL = ARTIFACT_DIR / f"{STEM}_board_proxy.stl"
RENDER_PATH = ARTIFACT_DIR / f"{STEM}_render.png"
REAR_RENDER_PATH = ARTIFACT_DIR / f"{STEM}_rear_alignment_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


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


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_x_cylinder(name: str, radius: float, depth: float, location: tuple[float, float, float], mat, vertices: int = 96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=(0, radians(90), 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def add_box(name: str, dimensions: tuple[float, float, float], location: tuple[float, float, float], mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def import_stl(path: Path, name: str, mat):
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def setup_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    params = manifest["params"]
    ref = manifest["reference_geometry"]

    mats = {
        "holder": material("matte warm gray printed holder", (0.62, 0.62, 0.56, 1.0), 0.68),
        "board": material("transparent blue GY-302 board proxy", (0.02, 0.24, 0.82, 0.68), 0.45),
        "axis": material("warm optical axis", (1.0, 0.74, 0.08, 0.82), 0.24),
        "mount": material("silver board mount pins", (0.82, 0.82, 0.78, 0.9), 0.3, 0.4),
        "sensor": material("black BH1750 package", (0.02, 0.025, 0.025, 1.0), 0.4),
        "pd": material("gold photodiode datum", (1.0, 0.82, 0.18, 1.0), 0.32, 0.05),
        "header": material("cream 1x5 header clearance proxy", (0.93, 0.88, 0.72, 0.74), 0.5),
    }

    import_stl(HOLDER_STL, "printed holder with OpenHI female C-mount receiver", mats["holder"])
    import_stl(BOARD_STL, "GY-302 BH1750 board proxy, sensor centered", mats["board"])

    total_len = params["female_socket_length_mm"] + params["tube_length_mm"] + params["sensor_plate_thickness_mm"]
    add_x_cylinder("optical axis through C-mount and BH1750 photodiode", 0.45, total_len + 8.0, (total_len / 2.0 - 1.5, 0, 0), mats["axis"], vertices=48)

    for hole in ref["mounting_holes_relative_to_sensor_mm"]:
        add_x_cylinder(
            f"{hole['name']} estimated board mount pin",
            hole["source_diameter_mm"] / 2.0,
            9.5,
            (total_len - 1.2, hole["y"], hole["z"]),
            mats["mount"],
            vertices=48,
        )

    add_box(
        "BH1750 package centered on optical axis",
        (
            params["bh1750_package_thickness_x_mm"],
            params["bh1750_package_width_y_mm"],
            params["bh1750_package_height_z_mm"],
        ),
        (total_len + params["board_thickness_mm"] + 0.4, 0, 0),
        mats["sensor"],
    )
    add_box(
        "BH1750 photodiode datum",
        (0.12, params["bh1750_pd_area_width_y_mm"], params["bh1750_pd_area_height_z_mm"]),
        (total_len + params["board_thickness_mm"] + params["bh1750_package_thickness_x_mm"] + 0.06, 0, 0),
        mats["pd"],
    )
    add_box(
        "1x5 header clearance proxy",
        (6.5, params["header_relief_width_y_mm"], 4.0),
        (total_len + params["board_thickness_mm"] + 3.1, 0, params["header_relief_z_mm"]),
        mats["header"],
    )

    bpy.ops.object.light_add(type="AREA", location=(-20, -40, 45))
    key = bpy.context.object
    key.name = "large key softbox"
    key.data.energy = 2400
    key.data.size = 7.5
    bpy.ops.object.light_add(type="AREA", location=(45, 30, 32))
    fill = bpy.context.object
    fill.name = "rear fill softbox"
    fill.data.energy = 1100
    fill.data.size = 10.0
    bpy.ops.object.light_add(type="AREA", location=(10, 25, 58))
    top = bpy.context.object
    top.name = "top alignment softbox"
    top.data.energy = 950
    top.data.size = 11.0

    bpy.ops.object.camera_add(location=(88, -96, 58), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (19, 0, 0))
    cam.data.lens = 62
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 64
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1300
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 1.2
    bpy.context.scene.world.color = (1, 1, 1)


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], lens: float, ortho: bool = False, ortho_scale: float = 58.0) -> None:
    cam = bpy.context.scene.camera
    cam.location = camera_location
    look_at(cam, target)
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    else:
        cam.data.type = "PERSP"
        cam.data.lens = lens
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    setup_scene()
    render(RENDER_PATH, (88, -96, 58), (19, 0, 0), 62, ortho=True, ortho_scale=70)
    render(REAR_RENDER_PATH, (78, 0, 0), (37, 0, 0), 70, ortho=True, ortho_scale=48)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
