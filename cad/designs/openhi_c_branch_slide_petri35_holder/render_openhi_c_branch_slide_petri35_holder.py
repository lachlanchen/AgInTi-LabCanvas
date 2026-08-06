#!/usr/bin/env python3
"""Render the two-part C-branch holder, fit check, section, and print layout."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_c_branch_slide_petri35_holder"
HOLDER_Z = 12.8


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def material(name: str, rgba: tuple[float, float, float, float], metallic: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Alpha"].default_value = rgba[3]
    bsdf.inputs["Roughness"].default_value = 0.32 if not metallic else 0.24
    bsdf.inputs["Metallic"].default_value = metallic
    if rgba[3] < 1.0:
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True
    return mat


def import_stl(filename: str, name: str, mat, location=(0, 0, 0)):
    path = ARTIFACT_DIR / filename
    try:
        bpy.ops.wm.stl_import(filepath=str(path))
    except Exception:
        bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.location = location
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def look_at(obj, target) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def setup(camera_location, target, resolution=(1600, 1150), ortho_scale=145):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.curvature_ridge_factor = 1.7
    scene.display.shading.curvature_valley_factor = 1.4
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.94, 0.96, 0.98)
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    look_at(camera, target)
    scene.camera = camera


def ground(size=300, z=-0.1):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    bpy.context.object.data.materials.append(material("ground", (0.18, 0.21, 0.26, 1.0)))


def render(path: Path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def assembly_render(mats):
    clear_scene()
    import_stl(
        f"{STEM}_c_branch_socket_male30_thread.stl",
        "C branch socket and male thread",
        mats["socket"],
    )
    import_stl(
        f"{STEM}_sample_holder_female30_thread.stl",
        "sample holder and female thread",
        mats["holder"],
        (0, 0, HOLDER_Z),
    )
    ground(z=-0.12)
    setup((132, -155, 104), (0, 0, 12), ortho_scale=150)
    render(ARTIFACT_DIR / f"{STEM}_assembly_render.png")


def exploded_render(mats):
    clear_scene()
    import_stl(
        f"{STEM}_c_branch_socket_male30_thread.stl",
        "socket with male thread",
        mats["socket"],
        (0, 0, -8),
    )
    import_stl(
        f"{STEM}_sample_holder_female30_thread.stl",
        "holder with female thread",
        mats["holder"],
        (0, 0, 30),
    )
    ground(z=-8.12)
    setup((142, -168, 118), (0, 0, 17), ortho_scale=165)
    render(ARTIFACT_DIR / f"{STEM}_exploded_render.png")


def fit_render(mats):
    clear_scene()
    import_stl(
        f"{STEM}_c_branch_socket_male30_thread.stl",
        "transparent socket",
        mats["socket_fit"],
    )
    import_stl(
        f"{STEM}_sample_holder_female30_thread.stl",
        "sample holder",
        mats["holder"],
        (0, 0, HOLDER_Z),
    )
    import_stl(
        f"{STEM}_openhi_c_reference_visualization_only.stl",
        "measured OpenHI C branch",
        mats["reference"],
    )
    ground(z=-20.1)
    setup((120, -148, 83), (0, 0, 5), ortho_scale=145)
    render(ARTIFACT_DIR / f"{STEM}_c_branch_fit_render.png")


def section_render(mats):
    clear_scene()
    import_stl(
        f"{STEM}_thread_section.stl",
        "two-part thread and receiver section",
        mats["section"],
    )
    ground(size=130, z=-0.1)
    setup((0, -82, 12), (0, 0, 12), resolution=(1450, 1100), ortho_scale=44)
    render(ARTIFACT_DIR / f"{STEM}_thread_section_render.png")


def print_layout_render(mats):
    clear_scene()
    import_stl(
        f"{STEM}_sample_holder_female30_thread.stl",
        "print sample holder",
        mats["holder"],
        (-92, 0, 0),
    )
    import_stl(
        f"{STEM}_c_branch_socket_male30_thread_print.stl",
        "print C branch socket",
        mats["socket"],
        (70, 0, 0),
    )
    ground(size=390, z=-0.08)
    setup((-41, 0, 340), (-41, 0, 0), resolution=(1650, 1050), ortho_scale=300)
    render(ARTIFACT_DIR / f"{STEM}_two_part_print_layout_render.png")


def main() -> None:
    bpy.context.preferences.filepaths.save_version = 0
    mats = {
        "holder": material("warm gray holder", (0.60, 0.58, 0.51, 1.0)),
        "socket": material("blue socket", (0.05, 0.34, 0.76, 1.0)),
        "socket_fit": material("transparent blue socket", (0.05, 0.34, 0.76, 0.38)),
        "reference": material("orange C branch", (0.96, 0.32, 0.04, 1.0), 0.2),
        "section": material("cyan section", (0.04, 0.55, 0.65, 1.0)),
        "print": material("print graphite", (0.17, 0.28, 0.45, 1.0)),
    }
    assembly_render(mats)
    exploded_render(mats)
    fit_render(mats)
    section_render(mats)
    print_layout_render(mats)
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACT_DIR / f"{STEM}.blend"))


if __name__ == "__main__":
    main()
