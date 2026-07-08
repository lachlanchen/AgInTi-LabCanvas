#!/usr/bin/env python3
"""Render the direct-socket TSL25911 C-mount intensity module holder."""

from __future__ import annotations

import json
from math import radians
from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
CMOUNT_SOCKET_STL = ARTIFACT_DIR / f"{STEM}_cmount_socket.stl"
SENSOR_PLATE_STL = ARTIFACT_DIR / f"{STEM}_sensor_plate.stl"
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
        "cmount": material("matte dark gray independent C-mount socket", (0.47, 0.47, 0.42, 1.0), 0.68),
        "plate": material("matte warm gray independent sensor plate", (0.62, 0.62, 0.56, 1.0), 0.68),
        "board": material("transparent deep blue TSL25911 20x27 module board", (0.02, 0.22, 0.70, 0.66), 0.45),
        "axis": material("warm optical axis", (1.0, 0.74, 0.08, 0.82), 0.24),
        "mount": material("silver M2 board-mount hole pins", (0.82, 0.82, 0.78, 0.9), 0.3, 0.4),
        "sensor": material("gold TSL25911 package", (0.82, 0.62, 0.16, 1.0), 0.35, 0.1),
        "socket": material("cream XH2.54 5P socket clearance proxy", (0.93, 0.88, 0.72, 0.74), 0.5),
        "wire": material("transparent orange full edge wire/header exit clearance", (1.0, 0.52, 0.18, 0.34), 0.5),
    }

    import_stl(CMOUNT_SOCKET_STL, "independent nominal 25.4 threaded C-mount socket with 25.0 pilot", mats["cmount"])
    import_stl(SENSOR_PLATE_STL, "independent TSL25911 sensor plate holder", mats["plate"])
    import_stl(BOARD_STL, "TSL25911 20x27 board proxy, sensor 7.5mm from sensor-side edge", mats["board"])

    total_len = params["female_socket_length_mm"] + params["sensor_plate_thickness_mm"]
    add_x_cylinder("optical axis through C-mount and TSL25911 package", 0.45, total_len + 8.0, (total_len / 2.0 - 1.5, 0, 0), mats["axis"], vertices=48)

    for hole in ref["mounting_holes_relative_to_sensor_mm"]:
        add_x_cylinder(
            f"{hole['name']} M2 board-mount pin",
            hole["cut_diameter_mm"] / 2.0,
            9.5,
            (total_len - 1.2, hole["y"], hole["z"]),
            mats["mount"],
            vertices=48,
        )

    board_cmount_face_x = total_len + 0.05
    sensor_package_x = board_cmount_face_x - params["tsl25911_package_thickness_x_mm"] / 2.0
    add_box(
        "TSL25911 package centered on optical axis, C-mount-facing PCB side",
        (
            params["tsl25911_package_thickness_x_mm"],
            params["tsl25911_package_width_y_mm"],
            params["tsl25911_package_height_z_mm"],
        ),
        (sensor_package_x, 0, 0),
        mats["sensor"],
    )
    add_x_cylinder(
        "TSL25911 active aperture marker on C-mount side",
        params["tsl25911_window_diameter_mm"] / 2.0,
        1.4,
        (sensor_package_x - params["tsl25911_package_thickness_x_mm"] / 2.0 - 0.1, 0, 0),
        mats["axis"],
        vertices=48,
    )

    socket = ref["xh254_socket_relative_to_sensor_mm"]
    socket_y = (socket["y_min"] + socket["y_max"]) / 2.0
    socket_z = (socket["z_min"] + socket["z_max"]) / 2.0
    wire_exit = ref["wire_exit_relative_to_sensor_mm"]
    wire_y = (wire_exit["y_min"] + wire_exit["y_max"]) / 2.0
    wire_z = (wire_exit["z_min"] + wire_exit["z_max"]) / 2.0
    add_box(
        "full edge-open wire/header exit clearance",
        (
            params["xh254_5p_socket_height_x_mm"],
            wire_exit["y_max"] - wire_exit["y_min"],
            wire_exit["z_max"] - wire_exit["z_min"],
        ),
        (
            total_len + params["board_thickness_mm"] + params["xh254_5p_socket_height_x_mm"] / 2.0,
            wire_y,
            wire_z,
        ),
        mats["wire"],
    )
    add_box(
        "XH2.54 5P socket clearance proxy on connector edge",
        (
            params["xh254_5p_socket_height_x_mm"],
            params["xh254_5p_socket_depth_y_mm"],
            params["xh254_5p_socket_width_z_mm"],
        ),
        (
            total_len + params["board_thickness_mm"] + params["xh254_5p_socket_height_x_mm"] / 2.0,
            socket_y,
            socket_z,
        ),
        mats["socket"],
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
    render(RENDER_PATH, (72, -84, 52), (10, 0, 0), 62, ortho=True, ortho_scale=68)
    render(REAR_RENDER_PATH, (58, 0, 0), (19, 0, 0), 70, ortho=True, ortho_scale=58)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
