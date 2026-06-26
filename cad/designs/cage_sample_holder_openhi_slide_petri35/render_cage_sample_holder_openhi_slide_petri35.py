#!/usr/bin/env python3
"""Render the modular cage sample holder."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_sample_holder_openhi_slide_petri35"

FRAME_STL = ARTIFACT_DIR / f"{STEM}_frame.stl"
SLIDE_STL = ARTIFACT_DIR / f"{STEM}_slide_cartridge.stl"
PETRI_STL = ARTIFACT_DIR / f"{STEM}_petri_cartridge.stl"

SLIDE_RENDER = ARTIFACT_DIR / f"{STEM}_slide_assembly_render.png"
PETRI_RENDER = ARTIFACT_DIR / f"{STEM}_petri_assembly_render.png"
EXPLODED_RENDER = ARTIFACT_DIR / f"{STEM}_exploded_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"


P = {
    "frame_thickness": 6.0,
    "cartridge_thickness": 3.2,
    "cartridge_gap": 0.4,
    "slide_rail_height": 2.0,
    "petri_ring_height": 2.2,
    "openhi_strip": (72.96, 20.0, 1.1),
    "petri_diameter": 33.0,
    "rod_pitch": 30.0,
    "rod_diameter": 5.9,
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


def import_stl(path: Path, name: str, material, location: tuple[float, float, float] = (0, 0, 0)):
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.location = location
    obj.data.materials.clear()
    obj.data.materials.append(material)
    return obj


def cartridge_z() -> float:
    return P["frame_thickness"] / 2.0 + P["cartridge_gap"] + P["cartridge_thickness"] / 2.0


def add_rods(material) -> None:
    half = P["rod_pitch"] / 2.0
    for x in (-half, half):
        for y in (-half, half):
            add_cylinder_z("cage rod proxy", P["rod_diameter"] / 2.0, 25.0, (x, y, 3.0), material)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def setup_common() -> dict[str, object]:
    clear_scene()
    materials = {
        "frame": make_material("matte black cage frame", (0.09, 0.09, 0.085, 1.0), roughness=0.65),
        "slide": make_material("teal slide cartridge", (0.05, 0.38, 0.35, 1.0), roughness=0.58),
        "petri": make_material("violet petri cartridge", (0.24, 0.18, 0.36, 1.0), roughness=0.58),
        "rod": make_material("blue cage rods", (0.1, 0.45, 0.9, 0.42), roughness=0.35),
        "glass": make_material("transparent sample glass", (0.75, 0.96, 1.0, 0.38), roughness=0.18),
        "dish": make_material("transparent petri dish", (0.95, 0.95, 1.0, 0.36), roughness=0.18),
    }

    bpy.ops.object.light_add(type="AREA", location=(0, -45, 48))
    light = bpy.context.object
    light.name = "large softbox"
    light.data.energy = 820
    light.data.size = 6.5

    bpy.ops.object.light_add(type="AREA", location=(-40, 30, 32))
    fill = bpy.context.object
    fill.name = "fill light"
    fill.data.energy = 260
    fill.data.size = 9.0

    bpy.ops.object.camera_add(location=(58, -64, 42), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (0, 0, 3))
    cam.data.lens = 58
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 48
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1100
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.world.color = (1, 1, 1)
    return materials


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], lens: float = 58) -> None:
    cam = bpy.context.scene.camera
    cam.location = camera_location
    look_at(cam, target)
    cam.data.type = "PERSP"
    cam.data.lens = lens
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_slide() -> None:
    materials = setup_common()
    z = cartridge_z()
    import_stl(FRAME_STL, "hollow cage frame", materials["frame"])
    import_stl(SLIDE_STL, "OpenHI strip cartridge", materials["slide"], (0, 0, z))
    add_rods(materials["rod"])
    add_box(
        "OpenHI strip proxy",
        P["openhi_strip"],
        (0, 0, z + P["cartridge_thickness"] / 2.0 + P["slide_rail_height"] + P["openhi_strip"][2] / 2.0),
        materials["glass"],
    )
    render(SLIDE_RENDER, (58, -64, 42), (0, 0, 4), 58)


def render_petri() -> None:
    materials = setup_common()
    z = cartridge_z()
    import_stl(FRAME_STL, "hollow cage frame", materials["frame"])
    import_stl(PETRI_STL, "33 mm petri cartridge", materials["petri"], (0, 0, z))
    add_rods(materials["rod"])
    add_cylinder_z(
        "33 mm petri dish proxy",
        P["petri_diameter"] / 2.0,
        1.2,
        (0, 0, z + P["cartridge_thickness"] / 2.0 + P["petri_ring_height"] + 0.6),
        materials["dish"],
    )
    render(PETRI_RENDER, (58, -64, 42), (0, 0, 4), 58)


def render_exploded() -> None:
    materials = setup_common()
    import_stl(FRAME_STL, "hollow cage frame", materials["frame"])
    import_stl(SLIDE_STL, "slide cartridge alternate", materials["slide"], (0, -37, 11))
    import_stl(PETRI_STL, "petri cartridge alternate", materials["petri"], (0, 37, 11))
    add_rods(materials["rod"])
    render(EXPLODED_RENDER, (64, -82, 54), (0, 0, 6), 64)


def main() -> None:
    render_slide()
    render_petri()
    render_exploded()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
