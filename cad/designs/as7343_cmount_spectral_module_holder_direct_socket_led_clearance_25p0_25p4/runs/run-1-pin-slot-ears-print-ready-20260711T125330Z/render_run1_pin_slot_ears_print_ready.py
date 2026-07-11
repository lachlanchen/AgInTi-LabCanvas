#!/usr/bin/env python3
"""Render the AS7343 print-ready run with four anti-warp ears."""

from __future__ import annotations

import shutil
from pathlib import Path

import bpy
from mathutils import Vector


RUN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = RUN_DIR / "artifacts"
STEM = "as7343_pin_slot_ears_print_ready"
PRINT_STL = RUN_DIR / f"PRINT_THIS_{STEM}.stl"
RENDER_PATH = RUN_DIR / f"PRINT_THIS_{STEM}_render.png"
BLEND_PATH = ARTIFACT_DIR / f"{STEM}.blend"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4"
    / RUN_DIR.name
)


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Alpha"].default_value = color[3]
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def look_at(obj, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    holder_mat = material("matte graphite AS7343 holder with print ears", (0.35, 0.35, 0.31, 1.0), 0.68)
    bed_mat = material("matte white print bed", (0.86, 0.88, 0.89, 1.0), 0.72)

    bpy.ops.import_mesh.stl(filepath=str(PRINT_STL))
    holder = bpy.context.object
    holder.name = "PRINT_THIS_AS7343_holder_rear_face_down_with_four_ears"
    holder.data.materials.clear()
    holder.data.materials.append(holder_mat)

    bpy.ops.mesh.primitive_plane_add(size=92, location=(0, 0, -0.035))
    bed = bpy.context.object
    bed.name = "print bed"
    bed.data.materials.append(bed_mat)

    bpy.ops.object.light_add(type="AREA", location=(-42, -38, 56))
    key = bpy.context.object
    key.name = "large print softbox"
    key.data.energy = 850
    key.data.size = 18.0
    bpy.ops.object.light_add(type="AREA", location=(42, 34, 48))
    fill = bpy.context.object
    fill.name = "soft fill"
    fill.data.energy = 350
    fill.data.size = 14.0

    bpy.ops.object.camera_add(location=(56, -62, 42), rotation=(0, 0, 0))
    cam = bpy.context.object
    look_at(cam, (0, 0, 6.0))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 108
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.show_shadows = True
    bpy.context.scene.render.resolution_x = 1700
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.world.color = (1, 1, 1)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    setup_scene()
    bpy.context.scene.render.filepath = str(RENDER_PATH)
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RENDER_PATH, NUTSTORE_DIR / RENDER_PATH.name)


if __name__ == "__main__":
    main()
