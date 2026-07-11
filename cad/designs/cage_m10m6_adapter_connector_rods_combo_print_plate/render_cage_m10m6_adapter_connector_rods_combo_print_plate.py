#!/usr/bin/env python3
"""Render the combined cage-system print plate."""

from __future__ import annotations

from mathutils import Vector
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_m10m6_adapter_connector_rods_combo_print_plate"
RENDER = ARTIFACT_DIR / f"{STEM}_render.png"
CLEARANCE = 8.0

SOURCES = {
    "rods_5x5": {
        "stl": ROOT
        / "cad/designs/cage_rods_50mm_m6/PRINT_THIS_cage_rods_50mm_m6_25rod_print_grid.stl",
        "color": (0.70, 0.70, 0.66, 1.0),
    },
    "connectors_3x3": {
        "stl": ROOT
        / "cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.stl",
        "color": (0.14, 0.14, 0.13, 1.0),
    },
    "adapters_2x2": {
        "stl": ROOT
        / "cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.stl",
        "color": (0.36, 0.32, 0.24, 1.0),
    },
}


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
        bsdf.inputs["Roughness"].default_value = 0.55
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def import_stl(path: Path, name: str, mat: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.import_mesh.stl(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return obj


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    max_v = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return min_v, max_v


def size_xy(obj: bpy.types.Object) -> tuple[float, float]:
    min_v, max_v = world_bounds(obj)
    return max_v.x - min_v.x, max_v.y - min_v.y


def place_min(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    min_v, _ = world_bounds(obj)
    obj.location.x += target[0] - min_v.x
    obj.location.y += target[1] - min_v.y
    obj.location.z += target[2] - min_v.z


def setup_scene() -> None:
    clear_scene()
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.show_shadows = True
    bpy.context.scene.world = bpy.data.worlds.new("World") if bpy.context.scene.world is None else bpy.context.scene.world
    bpy.context.scene.world.color = (1.0, 1.0, 1.0)
    bpy.context.scene.render.resolution_x = 1900
    bpy.context.scene.render.resolution_y = 1250
    bpy.ops.object.light_add(type="AREA", location=(115, -155, 165))
    light = bpy.context.object
    light.name = "large_softbox"
    light.data.energy = 520
    light.data.size = 95
    bpy.ops.object.camera_add(location=(250, -235, 190))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 340
    bpy.context.scene.camera = camera


def add_ground() -> None:
    ground_mat = material("matte_ground", (0.88, 0.90, 0.92, 1.0))
    bpy.ops.mesh.primitive_plane_add(size=390, location=(141, 58, -0.03))
    ground = bpy.context.object
    ground.name = "print_plate_ground"
    ground.data.materials.append(ground_mat)


def main() -> None:
    for source in SOURCES.values():
        if not source["stl"].exists():
            raise SystemExit(f"Missing STL input: {source['stl']}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    setup_scene()
    mats = {name: material(name, source["color"]) for name, source in SOURCES.items()}
    objects = {
        name: import_stl(source["stl"], name, mats[name])
        for name, source in SOURCES.items()
    }
    rods_w, rods_h = size_xy(objects["rods_5x5"])
    connectors_w, _ = size_xy(objects["connectors_3x3"])
    y_above_rods = rods_h + CLEARANCE
    placements = {
        "rods_5x5": (0.0, 0.0, 0.0),
        "connectors_3x3": (0.0, y_above_rods, 0.0),
        "adapters_2x2": (connectors_w + CLEARANCE, y_above_rods, 0.0),
    }
    for name, target in placements.items():
        place_min(objects[name], target)

    add_ground()
    camera = bpy.context.scene.camera
    look_at(camera, (rods_w / 2.0, y_above_rods / 2.0, 25.0))
    bpy.context.scene.render.filepath = str(RENDER)
    bpy.ops.render.render(write_still=True)
    print(RENDER)


if __name__ == "__main__":
    main()
