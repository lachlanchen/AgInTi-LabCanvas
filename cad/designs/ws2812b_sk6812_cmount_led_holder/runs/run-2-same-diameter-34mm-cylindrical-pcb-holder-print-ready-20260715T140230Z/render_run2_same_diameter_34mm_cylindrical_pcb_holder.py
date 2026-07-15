#!/usr/bin/env python3
"""Render the exact run-2 print geometry and the preserved proxy assembly."""

from __future__ import annotations

import math
from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = RUN_DIR / "artifacts"
STEM = "ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical"

SOCKET_STL = ARTIFACT_DIR / f"{STEM}_cmount_socket.stl"
PLATE_STL = ARTIFACT_DIR / f"{STEM}_cylindrical_holder_plate.stl"
BOARD_STL = ARTIFACT_DIR / f"{STEM}_board_proxy.stl"
PRINT_OUT = RUN_DIR / f"PRINT_THIS_{STEM}_render.png"
ASSEMBLY_OUT = ARTIFACT_DIR / f"{STEM}_assembly_with_proxies_render.png"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.5) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def import_stl(path: Path, name: str, mat: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def add_box(
    name: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    mat: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new(name="small proxy edge bevel", type="BEVEL")
    bevel.width = 0.18
    bevel.segments = 2
    return obj


def add_axis(mat: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.35, depth=18.0, location=(6.0, 0.0, 0.0))
    axis = bpy.context.object
    axis.name = "optical axis proxy"
    axis.rotation_euler[1] = math.radians(90.0)
    axis.data.materials.append(mat)
    return axis


def add_ground() -> None:
    ground_mat = material("neutral ground", (0.72, 0.74, 0.76, 1.0), 0.72)
    bpy.ops.mesh.primitive_plane_add(size=180, location=(5.0, 0.0, -18.2))
    ground = bpy.context.object
    ground.name = "ground"
    ground.data.materials.append(ground_mat)


def setup_camera_and_lighting(target_x: float = 6.0) -> None:
    world = bpy.context.scene.world
    world.color = (0.94, 0.96, 0.98)
    bpy.ops.object.light_add(type="AREA", location=(42, -48, 62))
    key = bpy.context.object
    key.name = "large soft key"
    key.data.energy = 1050
    key.data.size = 55
    bpy.ops.object.light_add(type="AREA", location=(-28, 34, 28))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 620
    fill.data.size = 38
    bpy.ops.object.light_add(type="AREA", location=(25, 22, -5))
    rim = bpy.context.object
    rim.name = "lower rim"
    rim.data.energy = 380
    rim.data.size = 28

    bpy.ops.object.camera_add(location=(58, -62, 45))
    camera = bpy.context.object
    camera.name = "full view camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 48.0
    bpy.context.scene.camera = camera
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(target_x, 0.0, 0.0))
    target = bpy.context.object
    target.name = "camera target"
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target


def configure_render(path: Path) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_valley_factor = 1.35
    scene.display.shading.cavity_ridge_factor = 1.15
    scene.display.shading.show_shadows = True
    scene.display.shading.show_specular_highlight = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1500
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(path)


def render_direct_print() -> None:
    clear_scene()
    socket_mat = material("C-mount socket charcoal", (0.16, 0.18, 0.20, 1.0), 0.48)
    plate_mat = material("cylindrical PCB holder graphite", (0.28, 0.31, 0.34, 1.0), 0.54)
    import_stl(SOCKET_STL, "independent 5 mm C-mount socket", socket_mat)
    import_stl(PLATE_STL, "independent 5 mm cylindrical PCB holder", plate_mat)
    add_ground()
    setup_camera_and_lighting(target_x=5.0)
    configure_render(PRINT_OUT)
    bpy.ops.render.render(write_still=True)


def render_proxy_assembly() -> None:
    clear_scene()
    socket_mat = material("C-mount socket charcoal", (0.10, 0.10, 0.09, 1.0), 0.48)
    plate_mat = material("cylindrical PCB holder graphite", (0.18, 0.18, 0.16, 1.0), 0.54)
    board_mat = material("PCB proxy blue", (0.0, 0.24, 0.50, 1.0), 0.44)
    led_mat = material("LED proxy gold", (0.95, 0.82, 0.24, 1.0), 0.34)
    cap_mat = material("capacitor proxy green", (0.08, 0.76, 0.44, 1.0), 0.46)
    header_mat = material("header proxy red", (0.82, 0.18, 0.18, 1.0), 0.5)
    axis_mat = material("optical axis amber", (1.0, 0.72, 0.08, 1.0), 0.28)

    import_stl(SOCKET_STL, "independent 5 mm C-mount socket", socket_mat)
    import_stl(PLATE_STL, "independent 5 mm cylindrical PCB holder", plate_mat)
    import_stl(BOARD_STL, "shared 24 mm board proxy", board_mat)
    add_box("5050 LED proxy", (12.25, 0.0, 0.0), (1.2, 5.0, 5.0), led_mat)
    add_box("backside C_0603 proxy", (12.10, 0.0, -3.7), (0.7, 1.6, 0.8), cap_mat)
    add_box("J1 header head proxy", (13.75, -8.7, 0.0), (4.0, 2.54, 5.08), header_mat)
    add_box("J2 header head proxy", (13.75, 8.7, 0.0), (4.0, 2.54, 5.08), header_mat)
    add_axis(axis_mat)
    add_ground()
    setup_camera_and_lighting(target_x=6.5)
    configure_render(ASSEMBLY_OUT)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    render_direct_print()
    render_proxy_assembly()
    print(f"Rendered {PRINT_OUT}")
    print(f"Rendered {ASSEMBLY_OUT}")


if __name__ == "__main__":
    main()
