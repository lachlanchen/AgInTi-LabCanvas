#!/usr/bin/env python3
"""Render assembly, C fit, adapter section, and direct-print layout."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_c_branch_slide_petri35_holder"


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
    bsdf.inputs["Roughness"].default_value = 0.34 if not metallic else 0.26
    bsdf.inputs["Metallic"].default_value = metallic
    if rgba[3] < 1.0:
        mat.blend_method = "BLEND"
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


def add_box(name, dimensions, location, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def add_cylinder(name, diameter, depth, location, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=diameter / 2.0, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
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
    scene.display.shading.curvature_ridge_factor = 1.65
    scene.display.shading.curvature_valley_factor = 1.35
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.93, 0.95, 0.98)
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    look_at(camera, target)
    scene.camera = camera


def ground(size=260, z=-13.0):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    bpy.context.object.data.materials.append(material("ground", (0.19, 0.22, 0.27, 1.0)))


def render(path: Path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def assembly_render(mats):
    clear_scene()
    import_stl(f"{STEM}_bottom_tray.stl", "sample tray", mats["tray"])
    import_stl(f"{STEM}_c_branch_adapter.stl", "separate adapter", mats["adapter"])
    import_stl(f"{STEM}_top_frame.stl", "top frame", mats["top"], (0, 0, 26))
    add_box("accepted slide proxy", (72.96, 20.0, 1.0), (0, 0, 7.3), mats["slide"])
    add_cylinder("33mm petri proxy", 33.0, 1.2, (0, 0, 7.15), mats["petri"])
    ground()
    setup((130, -155, 112), (0, 0, 12), ortho_scale=145)
    render(ARTIFACT_DIR / f"{STEM}_assembly_render.png")


def exploded_render(mats):
    clear_scene()
    import_stl(f"{STEM}_c_branch_adapter.stl", "adapter", mats["adapter"], (0, 0, -12))
    import_stl(f"{STEM}_bottom_tray.stl", "tray", mats["tray"], (0, 0, 10))
    import_stl(f"{STEM}_top_frame.stl", "top", mats["top"], (0, 0, 56))
    ground(z=-25)
    setup((150, -175, 130), (0, 0, 22), ortho_scale=175)
    render(ARTIFACT_DIR / f"{STEM}_exploded_render.png")


def fit_render(mats):
    clear_scene()
    import_stl(f"{STEM}_bottom_tray.stl", "tray", mats["tray"])
    import_stl(f"{STEM}_c_branch_adapter.stl", "adapter", mats["adapter_fit"])
    import_stl(f"{STEM}_top_frame.stl", "top frame", mats["top"], (0, 0, 26))
    import_stl(
        f"{STEM}_openhi_c_reference_visualization_only.stl",
        "measured OpenHI C reference",
        mats["reference"],
    )
    ground(z=-45)
    setup((145, -165, 105), (0, 0, -2), ortho_scale=175)
    render(ARTIFACT_DIR / f"{STEM}_c_branch_fit_render.png")


def section_render(mats):
    clear_scene()
    import_stl(f"{STEM}_adapter_half_section.stl", "adapter section", mats["section"])
    ground(z=-13)
    setup((72, -92, 44), (0, 0, -5), resolution=(1400, 1050), ortho_scale=58)
    render(ARTIFACT_DIR / f"{STEM}_adapter_section_render.png")


def print_layout_render(mats):
    clear_scene()
    import_stl(f"{STEM}_all_parts_layout.stl", "all printable parts", mats["print"])
    ground(size=360, z=-0.05)
    setup((0, 0, 330), (0, 0, 0), resolution=(1500, 1250), ortho_scale=280)
    render(ARTIFACT_DIR / f"{STEM}_print_layout_render.png")


def main() -> None:
    bpy.context.preferences.filepaths.save_version = 0
    mats = {
        "tray": material("warm gray tray", (0.55, 0.54, 0.50, 1.0)),
        "top": material("ivory top", (0.82, 0.80, 0.72, 1.0)),
        "adapter": material("blue adapter", (0.06, 0.34, 0.76, 1.0)),
        "adapter_fit": material("transparent blue adapter", (0.06, 0.34, 0.76, 0.42)),
        "reference": material("orange reference", (0.95, 0.31, 0.04, 1.0), 0.15),
        "section": material("cyan section", (0.04, 0.55, 0.64, 1.0)),
        "print": material("print graphite", (0.18, 0.29, 0.46, 1.0)),
        "slide": material("cyan slide", (0.04, 0.78, 0.92, 0.42)),
        "petri": material("clear petri", (0.88, 0.95, 1.0, 0.30)),
    }
    assembly_render(mats)
    exploded_render(mats)
    fit_render(mats)
    section_render(mats)
    print_layout_render(mats)
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACT_DIR / f"{STEM}.blend"))


if __name__ == "__main__":
    main()
