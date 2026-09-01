#!/usr/bin/env python3
"""Render assembled, optical-axis, and exploded OpenHI 4f views."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name: str, color: tuple[float, float, float, float], metallic: float = 0.0, roughness: float = 0.42):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if color[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = color[3]
        bsdf.inputs["Transmission Weight"].default_value = 0.25
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
    return mat


def look_at(camera, target: Vector):
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_axis_curve(name: str, points: list[tuple[float, float, float]], mat):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.45
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for item, point in zip(spline.points, points):
        item.co = (*point, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def object_bounds(objects):
    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
    lower = Vector((
        min(point.x for point in corners),
        min(point.y for point in corners),
        min(point.z for point in corners),
    ))
    upper = Vector((
        max(point.x for point in corners),
        max(point.y for point in corners),
        max(point.z for point in corners),
    ))
    return lower, upper


def fit_orthographic_camera(camera, objects, aspect, margin=1.45):
    bpy.context.view_layer.update()
    world_corners = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
    world_to_camera = camera.matrix_world.inverted()
    camera_corners = [world_to_camera @ point for point in world_corners]
    width = max(point.x for point in camera_corners) - min(
        point.x for point in camera_corners
    )
    height = max(point.y for point in camera_corners) - min(
        point.y for point in camera_corners
    )
    camera.data.ortho_scale = max(height * margin, width * margin / aspect)


def set_material_color(mat, color):
    mat.diffuse_color = color
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    design_dir = args.design_dir.resolve()
    artifact_dir = design_dir / "artifacts"
    manifest = json.loads((artifact_dir / "manifest.json").read_text())
    render_dir = artifact_dir / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    body_mats = {
        "A": material("A", (0.28, 0.55, 0.82, 1.0), metallic=0.18),
        "A_C_BS": material("A_C_BS", (0.48, 0.54, 0.62, 1.0), metallic=0.24),
        "B": material("B", (0.25, 0.68, 0.48, 1.0), metallic=0.18),
        "C": material("C", (0.86, 0.46, 0.24, 1.0), metallic=0.18),
        "Lens_B_holder": material("Lens_B_holder", (0.61, 0.42, 0.78, 1.0), metallic=0.16),
        "Lens_C_holder": material("Lens_C_holder", (0.28, 0.66, 0.78, 1.0), metallic=0.16),
    }
    glass = material("Lens glass", (0.18, 0.75, 0.90, 0.42), roughness=0.12)
    bs_glass = material("Beam splitter", (0.78, 0.90, 1.0, 0.30), roughness=0.08)
    axis_mat = material("Optical axes", (0.95, 0.20, 0.08, 1.0), roughness=0.25)

    component_objects = {}
    for path in sorted((artifact_dir / "assembly_components").glob("*.stl")):
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = bpy.context.object
        obj.name = path.stem
        if path.stem.startswith("lens_"):
            obj.data.materials.append(glass)
        elif path.stem == "beam_splitter_reference":
            obj.data.materials.append(bs_glass)
        else:
            obj.data.materials.append(body_mats[path.stem])
        for polygon in obj.data.polygons:
            polygon.use_smooth = path.stem.startswith("lens_")
        component_objects[path.stem] = obj

    f = float(manifest["optical_layout"]["catalog_efl_mm"])
    b_axis_x = float(manifest["optical_layout"]["b_axis_x_mm"])
    axis_objects = [
        add_axis_curve(
            "A optical axis",
            [(255, 210, 600 - f - 18), (255, 210, 600)],
            axis_mat,
        ),
        add_axis_curve(
            "B optical axis",
            [(b_axis_x, 210, 600), (b_axis_x, 210, 600 + f + 18)],
            axis_mat,
        ),
        add_axis_curve(
            "C optical axis",
            [(255, 210, 600), (255 + f + 32, 210, 600)],
            axis_mat,
        ),
    ]

    bpy.ops.mesh.primitive_plane_add(size=320, location=(255, 210, 475))
    floor = bpy.context.object
    floor_mat = material("Floor", (0.055, 0.065, 0.075, 1.0), roughness=0.72)
    floor.data.materials.append(floor_mat)

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("OpenHI World")
        bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.12, 0.15, 0.19, 1.0)
    background.inputs["Strength"].default_value = 0.65
    for location, energy, size in [((140, 90, 800), 1900, 110), ((440, 330, 760), 1450, 95), ((180, 350, 540), 1050, 85)]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        look_at(light, Vector((255, 210, 600)))

    bpy.ops.object.camera_add(location=(470, 20, 790))
    camera = bpy.context.object
    look_at(camera, Vector((285, 210, 605)))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 270
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.filepath = str(render_dir / "openhi_4f_assembly.png")
    bpy.ops.render.render(write_still=True)

    camera.location = (440, -20, 625)
    look_at(camera, Vector((285, 210, 600)))
    camera.data.ortho_scale = 235
    scene.render.filepath = str(render_dir / "openhi_4f_optical_axis.png")
    bpy.ops.render.render(write_still=True)

    # Explode only for this final view. Every part remains on its true mating
    # axis, while the beam-splitter proxy moves toward the viewer so it is not
    # hidden inside the two central bodies.
    gap = max(18.0, min(28.0, f * 0.45))
    exploded_offsets = {
        "A": (0.0, 0.0, -1.65 * gap),
        "lens_A": (0.0, 0.0, -0.85 * gap),
        "A_C_BS": (0.0, 0.0, 0.0),
        "Lens_B_holder": (0.0, 0.0, 0.45 * gap),
        "lens_B": (0.0, 0.0, 1.05 * gap),
        "B": (0.0, 0.0, 1.70 * gap),
        "Lens_C_holder": (0.45 * gap, 0.0, 0.0),
        "lens_C": (1.05 * gap, 0.0, 0.0),
        "C": (1.70 * gap, 0.0, 0.0),
        "beam_splitter_reference": (0.0, -1.05 * gap, 0.0),
    }
    for name, offset in exploded_offsets.items():
        component_objects[name].location += Vector(offset)
    bpy.context.view_layer.update()
    for obj in axis_objects:
        obj.hide_render = True
    exploded_axes = [
        add_axis_curve(
            "Exploded A guide",
            [(255, 210, 600 - f - 18 - 1.85 * gap), (255, 210, 600)],
            axis_mat,
        ),
        add_axis_curve(
            "Exploded B guide",
            [(b_axis_x, 210, 600), (b_axis_x, 210, 600 + f + 18 + 1.90 * gap)],
            axis_mat,
        ),
        add_axis_curve(
            "Exploded C guide",
            [(255, 210, 600), (255 + f + 32 + 1.90 * gap, 210, 600)],
            axis_mat,
        ),
    ]
    for obj in exploded_axes:
        obj.data.bevel_depth = 0.32

    lower, upper = object_bounds(component_objects.values())
    center = (lower + upper) / 2.0
    span = upper - lower
    floor.location.x = center.x
    floor.location.y = center.y
    floor.location.z = lower.z - 18.0
    floor.scale = (
        max(1.0, (span.x + 120.0) / 320.0),
        max(1.0, (span.y + 160.0) / 320.0),
        1.0,
    )
    set_material_color(floor_mat, (0.075, 0.09, 0.11, 1.0))
    background.inputs["Color"].default_value = (0.12, 0.15, 0.19, 1.0)
    background.inputs["Strength"].default_value = 0.62

    view_direction = Vector((1.15, -1.30, 1.05)).normalized()
    camera.location = center + view_direction * 520.0
    look_at(camera, center)
    aspect = scene.render.resolution_x / scene.render.resolution_y
    fit_orthographic_camera(
        camera,
        [*component_objects.values(), *exploded_axes],
        aspect,
        margin=1.65,
    )
    floor.hide_render = True
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_specular_highlight = True
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.055, 0.07, 0.09)
    scene.render.filepath = str(render_dir / "openhi_4f_spatial_exploded.png")
    bpy.ops.render.render(write_still=True)

    # Show the exact local orientations used by the separate print STL/3MF
    # files. This is a preview only; each part remains its own one-object file.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    scene.camera = camera
    print_objects = []
    part_paths = sorted((artifact_dir / "parts").glob("openhi_*.stl"))
    rows = (part_paths[:3], part_paths[3:])
    y_cursor = 0.0
    for row in rows:
        x_cursor = 0.0
        row_depth = 0.0
        for path in row:
            bpy.ops.wm.stl_import(filepath=str(path))
            obj = bpy.context.object
            key = path.stem.removeprefix("openhi_")
            obj.name = f"PRINT_THIS_{key}"
            obj.data.materials.append(body_mats[key])
            lower, upper = object_bounds([obj])
            obj.location += Vector(
                (x_cursor - lower.x, y_cursor - lower.y, -lower.z)
            )
            bpy.context.view_layer.update()
            lower, upper = object_bounds([obj])
            x_cursor = upper.x + 18.0
            row_depth = max(row_depth, upper.y - y_cursor)
            print_objects.append(obj)
        y_cursor += row_depth + 18.0

    lower, upper = object_bounds(print_objects)
    center = (lower + upper) / 2.0
    span = upper - lower
    bpy.ops.mesh.primitive_plane_add(
        size=max(span.x, span.y) + 80.0,
        location=(center.x, center.y, lower.z - 0.4),
    )
    print_floor = bpy.context.object
    print_floor.data.materials.append(floor_mat)
    camera.location = center + Vector((1.1, -1.2, 1.35)).normalized() * 420.0
    look_at(camera, center)
    fit_orthographic_camera(
        camera,
        print_objects,
        scene.render.resolution_x / scene.render.resolution_y,
        margin=1.55,
    )
    scene.render.filepath = str(render_dir / "openhi_4f_print_parts_layout.png")
    bpy.ops.render.render(write_still=True)

    # Inspection-only half sections expose the exact A input receiver, its
    # lifted 45-degree transition, and the fully inserted A lens cavity. These
    # are deliberately separate from the printable part files.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    inspection_objects = []
    for name in ("A", "A_C_BS"):
        path = artifact_dir / "inspection" / f"openhi_{name}_half_section.stl"
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = bpy.context.object
        obj.name = f"INSPECTION_{name}"
        obj.data.materials.append(body_mats[name])
        inspection_objects.append(obj)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    scene.camera = camera
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.055, 0.07, 0.09)

    # First isolate A so the internal receiver thread cannot be hidden by the
    # central body.
    inspection_objects[1].hide_render = True
    lower, upper = object_bounds([inspection_objects[0]])
    center = (lower + upper) / 2.0
    camera.location = center + Vector((0.12, 1.0, 0.08)).normalized() * 260.0
    look_at(camera, center)
    fit_orthographic_camera(
        camera,
        [inspection_objects[0]],
        scene.render.resolution_x / scene.render.resolution_y,
        margin=1.55,
    )
    scene.render.filepath = str(
        render_dir / "openhi_4f_a_input_receiver_section.png"
    )
    bpy.ops.render.render(write_still=True)

    # Then show the mating A holder section and the real lens B-rep together.
    inspection_objects[1].hide_render = False
    lens_path = artifact_dir / "assembly_components" / "lens_A.stl"
    bpy.ops.wm.stl_import(filepath=str(lens_path))
    lens_obj = bpy.context.object
    lens_obj.name = "INSPECTION_lens_A"
    lens_obj.data.materials.append(glass)
    for polygon in lens_obj.data.polygons:
        polygon.use_smooth = True
    section_assembly = [*inspection_objects, lens_obj]
    lower, upper = object_bounds(section_assembly)
    center = (lower + upper) / 2.0
    camera.location = center + Vector((0.12, 1.0, 0.08)).normalized() * 360.0
    look_at(camera, center)
    fit_orthographic_camera(
        camera,
        section_assembly,
        scene.render.resolution_x / scene.render.resolution_y,
        margin=1.60,
    )
    scene.render.filepath = str(
        render_dir / "openhi_4f_a_lens_cavity_section.png"
    )
    bpy.ops.render.render(write_still=True)

    # The run-5 C pair is sectioned after all helical booleans have been
    # completed and rotated onto X. This view proves that neither final solid
    # silently degraded to a smooth pilot cylinder.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    c_section_objects = []
    for name in ("C", "Lens_C_holder"):
        path = artifact_dir / "inspection" / f"openhi_{name}_half_section.stl"
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = bpy.context.object
        obj.name = f"INSPECTION_{name}"
        obj.data.materials.append(body_mats[name])
        c_section_objects.append(obj)
    lens_path = artifact_dir / "assembly_components" / "lens_C.stl"
    bpy.ops.wm.stl_import(filepath=str(lens_path))
    lens_obj = bpy.context.object
    lens_obj.name = "INSPECTION_lens_C"
    lens_obj.data.materials.append(glass)
    for polygon in lens_obj.data.polygons:
        polygon.use_smooth = True
    c_section_objects.append(lens_obj)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    scene.camera = camera
    lower, upper = object_bounds(c_section_objects)
    center = (lower + upper) / 2.0
    camera.location = center + Vector((0.08, 1.0, 0.12)).normalized() * 360.0
    look_at(camera, center)
    fit_orthographic_camera(
        camera,
        c_section_objects,
        scene.render.resolution_x / scene.render.resolution_y,
        margin=1.55,
    )
    scene.render.filepath = str(
        render_dir / "openhi_4f_c_lens_thread_section.png"
    )
    bpy.ops.render.render(write_still=True)

    # Isolate the two output caps in their checked print orientations. The
    # broad cylindrical grip now ends at a flat shoulder around the protruding
    # C-mount-style thread; this is intentionally support-dependent.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    grip_objects = []
    x_cursor = 0.0
    for name in ("B", "C"):
        path = artifact_dir / "parts" / f"openhi_{name}.stl"
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = bpy.context.object
        obj.name = f"STRAIGHT_GRIP_{name}"
        obj.data.materials.append(body_mats[name])
        lower, upper = object_bounds([obj])
        obj.location += Vector((x_cursor - lower.x, -lower.y, -lower.z))
        bpy.context.view_layer.update()
        lower, upper = object_bounds([obj])
        x_cursor = upper.x + 24.0
        grip_objects.append(obj)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    scene.camera = camera
    lower, upper = object_bounds(grip_objects)
    center = (lower + upper) / 2.0
    camera.location = center + Vector((1.15, -1.35, 1.0)).normalized() * 360.0
    look_at(camera, center)
    fit_orthographic_camera(
        camera,
        grip_objects,
        scene.render.resolution_x / scene.render.resolution_y,
        margin=1.5,
    )
    scene.render.filepath = str(
        render_dir / "openhi_4f_b_c_straight_camera_grips.png"
    )
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
