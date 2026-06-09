"""Render the C-mount reflector adapter STL with Blender.

Run with:
    blender --background --python blender_render.py
"""

from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
STL = ARTIFACTS / "cmount_reflector_adapter.stl"
PNG = ARTIFACTS / "adapter_render_blender.png"
BLEND = ARTIFACTS / "cmount_reflector_adapter.blend"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_stl():
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=str(STL))
    else:
        bpy.ops.import_mesh.stl(filepath=str(STL))
    obj = bpy.context.object
    obj.name = "C-mount reflector adapter"
    return obj


def make_material(name, color, roughness=0.58):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def setup_scene(obj):
    obj.data.materials.append(make_material("satin printed polymer", (0.42, 0.76, 0.92, 1.0)))
    obj.rotation_euler[2] = 0.0

    bounds = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    center = sum(bounds, Vector()) / 8
    size = Vector(
        (
            max(v.x for v in bounds) - min(v.x for v in bounds),
            max(v.y for v in bounds) - min(v.y for v in bounds),
            max(v.z for v in bounds) - min(v.z for v in bounds),
        )
    )

    bpy.ops.mesh.primitive_plane_add(size=95, location=(center.x + 7, 0, -0.05))
    plane = bpy.context.object
    plane.name = "matte reference floor"
    plane.data.materials.append(make_material("warm gray floor", (0.78, 0.80, 0.82, 1.0)))

    bpy.ops.object.light_add(type="AREA", location=(20, -32, 55))
    key = bpy.context.object
    key.name = "large softbox"
    key.data.energy = 720
    key.data.size = 7

    bpy.ops.object.light_add(type="AREA", location=(-25, 24, 28))
    fill = bpy.context.object
    fill.name = "fill light"
    fill.data.energy = 260
    fill.data.size = 9

    camera_location = (88, -76, 52)
    bpy.ops.object.camera_add(location=camera_location, rotation=(0, 0, 0))
    camera = bpy.context.object
    direction = center - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 62
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = obj
    camera.data.dof.aperture_fstop = 8
    bpy.context.scene.camera = camera

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 96
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 0.45
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.world.color = (0.95, 0.97, 0.99)

    return size


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    clear_scene()
    obj = import_stl()
    size = setup_scene(obj)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    bpy.context.scene.render.filepath = str(PNG)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered {PNG}")
    print(f"Bounding size mm: {size.x:.2f} x {size.y:.2f} x {size.z:.2f}")


if __name__ == "__main__":
    main()
