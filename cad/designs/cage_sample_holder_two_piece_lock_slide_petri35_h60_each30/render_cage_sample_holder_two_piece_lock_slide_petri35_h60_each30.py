#!/usr/bin/env python3
"""Render the 60 mm two-piece locking sample holder."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_sample_holder_two_piece_lock_slide_petri35_h60_each30"

BOTTOM_STL = ARTIFACT_DIR / f"{STEM}_bottom_part.stl"
TOP_STL = ARTIFACT_DIR / f"{STEM}_top_part.stl"

ASSEMBLED_RENDER = ARTIFACT_DIR / f"{STEM}_assembled_render.png"
EXPLODED_RENDER = ARTIFACT_DIR / f"{STEM}_exploded_render.png"
PRINT_LAYOUT_RENDER = ARTIFACT_DIR / f"{STEM}_print_layout_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


P = {
    "bottom_body_height": 8.0,
    "top_frame_height": 30.0,
    "top_z": 30.0,
    "rod_diameter": 5.9,
    "top_rods": [(-30.0, 28.0), (30.0, 28.0)],
    "bottom_rods": [(-30.0, -28.0), (30.0, -28.0)],
    "slide": (72.96, 20.0, 1.0),
    "petri_diameter": 33.0,
}


def make_material(name: str, color: tuple[float, float, float, float], roughness: float = 0.55, metallic: float = 0.0):
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


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_stl(path: Path, name: str, material, location: tuple[float, float, float] = (0, 0, 0)):
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.location = location
    obj.data.materials.clear()
    obj.data.materials.append(material)
    return obj


def add_cylinder_z(name: str, radius: float, depth: float, location: tuple[float, float, float], material, vertices: int = 96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def add_box(name: str, dimensions: tuple[float, float, float], location: tuple[float, float, float], material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def setup_common() -> dict[str, object]:
    clear_scene()
    materials = {
        "bottom": make_material("warm gray bottom tray", (0.58, 0.57, 0.53, 1.0), roughness=0.64),
        "top": make_material("light ivory top frame", (0.82, 0.80, 0.72, 1.0), roughness=0.58),
        "rod": make_material("blue 6 mm rod proxies", (0.08, 0.48, 0.95, 0.50), roughness=0.32),
        "slide": make_material("cyan OpenHI slide proxy", (0.05, 0.85, 0.95, 0.50), roughness=0.2),
        "petri": make_material("clear petri dish proxy", (0.95, 0.95, 1.0, 0.42), roughness=0.18),
        "peg": make_material("lock fit highlight", (0.95, 0.68, 0.18, 0.52), roughness=0.35),
    }

    bpy.ops.object.light_add(type="AREA", location=(0, -74, 92))
    key = bpy.context.object
    key.name = "large softbox"
    key.data.energy = 5600
    key.data.size = 18.0

    bpy.ops.object.light_add(type="AREA", location=(-58, 56, 58))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 2300
    fill.data.size = 18.0

    bpy.ops.object.light_add(type="SUN", location=(0, 0, 80))
    sun = bpy.context.object
    sun.name = "low shadow fill sun"
    sun.data.energy = 1.6

    bpy.ops.object.camera_add(location=(82, -96, 66), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (0, 0, 14))
    cam.data.lens = 64
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 48
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1250
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
    bpy.context.scene.view_settings.exposure = 0.8
    bpy.context.scene.view_settings.gamma = 1.0
    bpy.context.scene.world.color = (1, 1, 1)
    return materials


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], lens: float = 64, *, ortho: bool = False, ortho_scale: float = 126.0) -> None:
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


def add_rods(material) -> None:
    for x, y in P["top_rods"]:
        add_cylinder_z("upper 6 mm rod proxy", P["rod_diameter"] / 2.0, 28.0, (x, y, P["top_z"] + P["top_frame_height"] + 13.5), material)
    for x, y in P["bottom_rods"]:
        add_cylinder_z("lower 6 mm rod proxy", P["rod_diameter"] / 2.0, 28.0, (x, y, -13.5), material)


def add_samples(materials) -> None:
    add_box("OpenHI slide strip proxy", P["slide"], (0, 0, P["bottom_body_height"] - 0.7), materials["slide"])
    add_cylinder_z("33 mm petri dish proxy", P["petri_diameter"] / 2.0, 1.2, (0, 0, P["bottom_body_height"] - 0.85), materials["petri"])


def render_assembled() -> None:
    materials = setup_common()
    import_stl(BOTTOM_STL, "bottom tray with lock feet", materials["bottom"])
    import_stl(TOP_STL, "top frame with lock sockets", materials["top"], (0, 0, P["top_z"]))
    add_rods(materials["rod"])
    add_samples(materials)
    render(ASSEMBLED_RENDER, (166, -192, 150), (0, 0, 30), 70, ortho=True, ortho_scale=184)


def render_exploded() -> None:
    materials = setup_common()
    import_stl(BOTTOM_STL, "bottom tray with lock feet", materials["bottom"])
    import_stl(TOP_STL, "top frame lifted to show lock holes", materials["top"], (0, 0, 78))
    add_rods(materials["rod"])
    add_box("OpenHI slide strip proxy", P["slide"], (0, -52, 14), materials["slide"])
    add_cylinder_z("33 mm petri dish proxy", P["petri_diameter"] / 2.0, 1.2, (0, 52, 13.4), materials["petri"])
    render(EXPLODED_RENDER, (190, -220, 184), (0, 0, 48), 72, ortho=True, ortho_scale=260)


def render_print_layout() -> None:
    materials = setup_common()
    import_stl(BOTTOM_STL, "print layout bottom part", materials["bottom"], (0, -62, 0))
    import_stl(TOP_STL, "print layout top part", materials["top"], (0, 62, 0))
    render(PRINT_LAYOUT_RENDER, (0, 0, 320), (0, 0, 0), 60, ortho=True, ortho_scale=360)


def main() -> None:
    bpy.context.preferences.filepaths.save_version = 0
    render_assembled()
    render_exploded()
    render_print_layout()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
