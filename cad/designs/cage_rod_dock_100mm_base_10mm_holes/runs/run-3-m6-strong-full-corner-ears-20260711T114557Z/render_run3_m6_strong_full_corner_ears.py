#!/usr/bin/env python3
"""Render run 3 M6 dock with strong full-corner ears."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_rod_dock_100mm_base_m6_strong_full_corner_ears"

DOCK_STL = ARTIFACT_DIR / f"{STEM}.stl"
RENDER = ARTIFACT_DIR / f"{STEM}_render.png"
ASSEMBLY_RENDER = ARTIFACT_DIR / f"{STEM}_assembly_render.png"

ROD_CENTERS = [(-15.0, -15.0), (15.0, -15.0), (-15.0, 15.0), (15.0, 15.0)]
BASE_THICKNESS = 30.0
ROD_DEPTH = 25.0
ROD_VISIBLE_HEIGHT = 72.0
ROD_DIAMETER = 6.0


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_material(name: str, color: tuple[float, float, float, float], roughness: float = 0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Alpha"].default_value = color[3]
        bsdf.inputs["Roughness"].default_value = roughness
    if color[3] < 1.0:
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True
    return mat


def import_stl(path: Path, name: str, material):
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.clear()
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def add_cylinder_z(name: str, radius: float, depth: float, location: tuple[float, float, float], material, vertices: int = 96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def setup_common() -> dict[str, object]:
    clear_scene()
    materials = {
        "dock": make_material("matte graphite dock", (0.17, 0.17, 0.16, 1.0), roughness=0.66),
        "rod": make_material("transparent blue cage rods", (0.08, 0.48, 0.95, 0.42), roughness=0.28),
        "ground": make_material("matte ground", (0.88, 0.90, 0.92, 1.0), roughness=0.7),
    }
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.show_shadows = True
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1350
    bpy.context.scene.world = bpy.data.worlds.new("World") if bpy.context.scene.world is None else bpy.context.scene.world
    bpy.context.scene.world.color = (1, 1, 1)

    bpy.ops.object.light_add(type="AREA", location=(-74, -92, 130))
    key = bpy.context.object
    key.name = "large softbox"
    key.data.energy = 600
    key.data.size = 52.0

    bpy.ops.object.camera_add(location=(176, -198, 138), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (0, 0, 18))
    cam.data.type = "ORTHO"
    bpy.context.scene.camera = cam

    bpy.ops.mesh.primitive_plane_add(size=260, location=(0, 0, -0.04))
    ground = bpy.context.object
    ground.name = "print bed ground"
    ground.data.materials.append(materials["ground"])
    return materials


def render(path: Path, camera_location: tuple[float, float, float], target: tuple[float, float, float], *, ortho_scale: float) -> None:
    cam = bpy.context.scene.camera
    cam.location = camera_location
    look_at(cam, target)
    cam.data.ortho_scale = ortho_scale
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_single() -> None:
    materials = setup_common()
    import_stl(DOCK_STL, "M6 dock with strong full-corner ears", materials["dock"])
    render(RENDER, (180, -210, 148), (0, 0, 10), ortho_scale=250)


def render_assembly() -> None:
    materials = setup_common()
    import_stl(DOCK_STL, "M6 dock with strong full-corner ears", materials["dock"])
    rod_depth = ROD_DEPTH + ROD_VISIBLE_HEIGHT
    rod_center_z = BASE_THICKNESS - ROD_DEPTH + rod_depth / 2.0
    for x, y in ROD_CENTERS:
        add_cylinder_z("6 mm cage rod proxy", ROD_DIAMETER / 2.0, rod_depth, (x, y, rod_center_z), materials["rod"])
    render(ASSEMBLY_RENDER, (180, -210, 166), (0, 0, 34), ortho_scale=255)


def main() -> None:
    if not DOCK_STL.exists():
        raise SystemExit(f"Missing STL input: {DOCK_STL}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    render_single()
    render_assembly()
    print(RENDER)
    print(ASSEMBLY_RENDER)


if __name__ == "__main__":
    main()
