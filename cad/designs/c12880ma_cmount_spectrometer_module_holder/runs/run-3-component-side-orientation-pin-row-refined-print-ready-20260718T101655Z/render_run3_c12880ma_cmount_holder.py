#!/usr/bin/env python3
"""Render C12880MA run 3 with the verified component-side orientation."""

from __future__ import annotations

import shutil
from pathlib import Path

import bpy


RUN_DIR = Path(__file__).resolve().parent
DESIGN_DIR = RUN_DIR.parents[1]
ARTIFACT_DIR = RUN_DIR / "artifacts"
LATEST_ARTIFACT_DIR = DESIGN_DIR / "artifacts"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / DESIGN_DIR.name
    / RUN_DIR.name
)
STEM = "c12880ma_cmount_holder_42x42_component_orientation_run3"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def material(
    name: str,
    color: tuple[float, float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.5,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def import_stl(path: Path, name: str, mat: bpy.types.Material) -> bpy.types.Object:
    try:
        bpy.ops.wm.stl_import(filepath=str(path))
    except Exception:
        bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def add_camera(
    location: tuple[float, float, float],
    target_location: tuple[float, float, float],
    ortho_scale: float,
) -> None:
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    bpy.context.scene.camera = camera
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=target_location)
    target = bpy.context.object
    target.hide_render = True
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target


def configure_scene(output: Path) -> None:
    scene = bpy.context.scene
    scene.world.color = (0.96, 0.97, 0.98)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.cavity_valley_factor = 1.6
    scene.display.shading.cavity_ridge_factor = 1.25
    scene.display.shading.show_shadows = True
    scene.display.shading.show_specular_highlight = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1450
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(output)


def render_print_body(holder_mat: bpy.types.Material) -> Path:
    clear_scene()
    output = RUN_DIR / f"PRINT_THIS_{STEM}_render.png"
    import_stl(
        RUN_DIR / f"PRINT_THIS_{STEM}.stl",
        "exact direct-print body",
        holder_mat,
    )
    add_camera((58.0, -69.0, 48.0), (0.0, 3.6, 10.0), 58.0)
    configure_scene(output)
    bpy.ops.render.render(write_still=True)
    return output


def render_measured_assembly(
    holder_mat: bpy.types.Material,
    board_mat: bpy.types.Material,
    sensor_mat: bpy.types.Material,
    pin_mat: bpy.types.Material,
) -> tuple[Path, Path]:
    clear_scene()
    output = RUN_DIR / f"{STEM}_assembly_render.png"
    import_stl(
        ARTIFACT_DIR / f"{STEM}_design_orientation.stl",
        "threaded C-mount holder",
        holder_mat,
    )
    board = import_stl(
        ARTIFACT_DIR / f"{STEM}_board_proxy.stl",
        "offset 38.3 x 22.8 PCB proxy",
        board_mat,
    )
    sensor = import_stl(
        ARTIFACT_DIR / f"{STEM}_sensor_package_proxy.stl",
        "C12880 package centered on optical axis",
        sensor_mat,
    )
    pins = import_stl(
        ARTIFACT_DIR / f"{STEM}_six_pin_tail_proxy.stl",
        "six solder tails inside connected relief",
        pin_mat,
    )
    # Pull the rear-installed module 11 mm outward as one rigid unit. This makes
    # the sensor-up/socket-down orientation visible without changing the optical
    # relationship between the package and C-mount.
    for obj in (board, sensor, pins):
        obj.location.x += 11.0
    add_camera((-54.0, -62.0, 45.0), (13.0, 2.0, -0.5), 61.0)
    configure_scene(output)
    bpy.ops.render.render(write_still=True)
    blend_path = ARTIFACT_DIR / f"{STEM}_assembly.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    return output, blend_path


def sync(paths: list[Path]) -> None:
    LATEST_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, LATEST_ARTIFACT_DIR / path.name)
        shutil.copy2(path, NUTSTORE_DIR / path.name)


def main() -> None:
    holder_mat = material("graphite printed holder", (0.22, 0.24, 0.27, 1.0), 0.0, 0.42)
    board_mat = material("spectrometer PCB", (0.02, 0.40, 0.19, 1.0), 0.0, 0.5)
    sensor_mat = material("sensor package", (0.68, 0.71, 0.74, 1.0), 0.65, 0.25)
    pin_mat = material("connector solder tails", (0.95, 0.48, 0.08, 1.0), 0.55, 0.24)
    print_render = render_print_body(holder_mat)
    assembly_render, blend_path = render_measured_assembly(
        holder_mat, board_mat, sensor_mat, pin_mat
    )
    sync([print_render, assembly_render, blend_path])


if __name__ == "__main__":
    main()
