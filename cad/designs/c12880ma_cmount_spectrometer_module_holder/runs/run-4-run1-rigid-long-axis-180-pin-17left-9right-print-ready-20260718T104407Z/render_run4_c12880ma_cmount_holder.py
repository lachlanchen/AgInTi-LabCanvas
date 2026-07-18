#!/usr/bin/env python3
"""Render C12880MA run 4 in table, exploded, and direct-print orientations."""

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
STEM = "c12880ma_cmount_holder_42x42_table_orientation_run4"


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


def add_table(table_mat: bpy.types.Material) -> None:
    bpy.ops.mesh.primitive_plane_add(size=86.0, location=(0.0, 3.6, -0.08))
    table = bpy.context.object
    table.name = "PCB table datum Z=0"
    table.data.materials.append(table_mat)


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


def import_table_parts(
    holder_mat: bpy.types.Material,
    board_mat: bpy.types.Material,
    sensor_mat: bpy.types.Material,
    pin_mat: bpy.types.Material,
) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object, bpy.types.Object]:
    holder = import_stl(
        ARTIFACT_DIR / f"{STEM}_table_orientation.stl",
        "run-1 holder rigidly rotated to component-side-up table coordinates",
        holder_mat,
    )
    board = import_stl(
        ARTIFACT_DIR / f"{STEM}_board_proxy.stl",
        "PCB component side up, sensor up and socket down",
        board_mat,
    )
    sensor = import_stl(
        ARTIFACT_DIR / f"{STEM}_sensor_package_proxy.stl",
        "C12880 package centered under the C-mount",
        sensor_mat,
    )
    pins = import_stl(
        ARTIFACT_DIR / f"{STEM}_six_pin_tail_proxy.stl",
        "six solder tails, 16.8 mm left and 8.8 mm right margins",
        pin_mat,
    )
    return holder, board, sensor, pins


def render_table_assembly(
    holder_mat: bpy.types.Material,
    board_mat: bpy.types.Material,
    sensor_mat: bpy.types.Material,
    pin_mat: bpy.types.Material,
    table_mat: bpy.types.Material,
) -> tuple[Path, Path]:
    clear_scene()
    output = RUN_DIR / f"{STEM}_assembly_render.png"
    import_table_parts(holder_mat, board_mat, sensor_mat, pin_mat)
    add_table(table_mat)
    add_camera((63.0, -66.0, 56.0), (0.0, 3.6, 8.0), 62.0)
    configure_scene(output)
    bpy.ops.render.render(write_still=True)
    blend_path = ARTIFACT_DIR / f"{STEM}_assembly.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    return output, blend_path


def render_exploded_alignment(
    holder_mat: bpy.types.Material,
    board_mat: bpy.types.Material,
    sensor_mat: bpy.types.Material,
    pin_mat: bpy.types.Material,
    table_mat: bpy.types.Material,
) -> Path:
    clear_scene()
    output = RUN_DIR / f"{STEM}_exploded_alignment_render.png"
    holder, _board, _sensor, _pins = import_table_parts(
        holder_mat, board_mat, sensor_mat, pin_mat
    )
    holder.location.z += 12.0
    add_table(table_mat)
    add_camera((67.0, -72.0, 64.0), (0.0, 3.6, 10.0), 67.0)
    configure_scene(output)
    bpy.ops.render.render(write_still=True)
    return output


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
    table_mat = material("table datum", (0.82, 0.84, 0.86, 1.0), 0.0, 0.85)
    print_render = render_print_body(holder_mat)
    assembly_render, blend_path = render_table_assembly(
        holder_mat, board_mat, sensor_mat, pin_mat, table_mat
    )
    exploded_render = render_exploded_alignment(
        holder_mat, board_mat, sensor_mat, pin_mat, table_mat
    )
    sync([print_render, assembly_render, exploded_render, blend_path])


if __name__ == "__main__":
    main()
