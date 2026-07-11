#!/usr/bin/env python3
"""Render the M10-hole to M6-rod adapter and its 2x2 print grid."""

from __future__ import annotations

from mathutils import Vector
from pathlib import Path
import math

import bpy


DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_dock_m10_to_m6_adapter_20_50"
SINGLE_STL = ARTIFACT_DIR / f"{STEM}.stl"
GRID_STL = ARTIFACT_DIR / f"{STEM}_2x2_print_grid.stl"
SINGLE_RENDER = ARTIFACT_DIR / f"{STEM}_render.png"
GRID_RENDER = ARTIFACT_DIR / f"{STEM}_2x2_print_grid_render.png"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.52
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def import_stl(path: Path, mat: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = path.stem
    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return obj


def setup_scene() -> None:
    clear_scene()
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.show_shadows = True
    bpy.context.scene.world = bpy.data.worlds.new("World") if bpy.context.scene.world is None else bpy.context.scene.world
    bpy.context.scene.world.color = (1.0, 1.0, 1.0)
    bpy.context.scene.render.resolution_x = 1700
    bpy.context.scene.render.resolution_y = 1250
    bpy.ops.object.light_add(type="AREA", location=(24, -42, 105))
    light = bpy.context.object
    light.name = "large_softbox"
    light.data.energy = 420
    light.data.size = 52
    bpy.ops.object.camera_add(location=(62, -82, 74))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 88
    bpy.context.scene.camera = camera


def add_ground(size: float = 100.0) -> None:
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, -0.02))
    ground = bpy.context.object
    ground.name = "matte_ground"
    ground.data.materials.append(material("matte_ground_material", (0.88, 0.90, 0.92, 1.0)))


def add_axis_hint(height: float = 70.0) -> None:
    mat = material("axis_hint_blue", (0.1, 0.22, 0.55, 1.0))
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.32, depth=height, location=(13.0, 0, height / 2.0))
    axis = bpy.context.object
    axis.name = "height_reference_70mm"
    axis.data.materials.append(mat)
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=1.1, depth=2.8, location=(13.0, 0, height + 1.4))
    arrow = bpy.context.object
    arrow.name = "height_reference_arrow"
    arrow.data.materials.append(mat)


def render_to(path: Path, *, camera_location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> None:
    camera = bpy.context.scene.camera
    camera.location = camera_location
    camera.data.ortho_scale = ortho_scale
    look_at(camera, target)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_single() -> None:
    setup_scene()
    adapter_mat = material("warm_gray_printed_plastic", (0.72, 0.71, 0.66, 1.0))
    import_stl(SINGLE_STL, adapter_mat)
    add_ground(70)
    add_axis_hint()
    render_to(SINGLE_RENDER, camera_location=(58, -82, 74), target=(0, 0, 32), ortho_scale=84)


def render_grid() -> None:
    setup_scene()
    adapter_mat = material("warm_gray_print_grid", (0.72, 0.71, 0.66, 1.0))
    import_stl(GRID_STL, adapter_mat)
    add_ground(96)
    render_to(GRID_RENDER, camera_location=(76, -92, 82), target=(0, 0, 30), ortho_scale=98)


def main() -> None:
    if not SINGLE_STL.exists() or not GRID_STL.exists():
        missing = [str(path) for path in (SINGLE_STL, GRID_STL) if not path.exists()]
        raise SystemExit(f"Missing STL input: {', '.join(missing)}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    render_single()
    render_grid()
    print(SINGLE_RENDER)
    print(GRID_RENDER)


if __name__ == "__main__":
    main()
