#!/usr/bin/env python3
"""Render publication-style views of the single- and dual-4f apparatus."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from blender_camera_fit import fit_camera_to_objects

CAMERA_RECORDS = []


PALETTE = {
    "polymer": (0.055, 0.065, 0.078, 1.0),
    "polymer_mid": (0.17, 0.19, 0.22, 1.0),
    "metal": (0.58, 0.63, 0.69, 1.0),
    "pcb": (0.025, 0.27, 0.12, 1.0),
    "glass": (0.24, 0.76, 0.90, 0.42),
    "polarizer": (0.08, 0.15, 0.24, 0.68),
    "sample": (0.05, 0.62, 0.52, 0.62),
    "camera": (0.055, 0.12, 0.21, 1.0),
    "event_camera": (0.32, 0.055, 0.045, 1.0),
    "sensor": (0.72, 0.75, 0.78, 1.0),
    "warm": (1.0, 0.62, 0.10, 1.0),
    "cyan": (0.04, 0.58, 0.88, 1.0),
    "green": (0.04, 0.68, 0.42, 1.0),
    "orange": (0.95, 0.24, 0.08, 1.0),
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--samples", type=int, default=64)
    return parser.parse_args(argv)


def material(name: str, rgba: tuple[float, float, float, float], *, metallic: float = 0.0, roughness: float = 0.42, emission: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.35
    if rgba[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = rgba[3]
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = min(0.75, 1.0 - rgba[3] + 0.25)
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
    if emission:
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = rgba
    return mat


def setup_scene(samples: int) -> dict[str, bpy.types.Material]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee"):
        for key, value in (("taa_render_samples", samples), ("use_gtao", True), ("gtao_distance", 80.0), ("use_soft_shadows", True)):
            try:
                setattr(scene.eevee, key, value)
            except Exception:
                pass
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 35
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.15
    world = scene.world or bpy.data.worlds.new("Publication World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.93, 0.945, 0.96, 1.0)
    background.inputs["Strength"].default_value = 0.72

    mats = {
        "polymer": material("Black printed polymer", PALETTE["polymer"], roughness=0.48),
        "polymer_mid": material("Graphite printed polymer", PALETTE["polymer_mid"], roughness=0.52),
        "metal": material("Brushed metal", PALETTE["metal"], metallic=0.68, roughness=0.23),
        "pcb": material("PCB", PALETTE["pcb"], roughness=0.36),
        "glass": material("Optical glass", PALETTE["glass"], roughness=0.08),
        "polarizer": material("Polarizer film", PALETTE["polarizer"], roughness=0.22),
        "sample": material("Sample", PALETTE["sample"], roughness=0.18),
        "camera": material("Frame camera", PALETTE["camera"], metallic=0.24, roughness=0.30),
        "event_camera": material("Event camera", PALETTE["event_camera"], metallic=0.20, roughness=0.32),
        "sensor": material("Sensor package", PALETTE["sensor"], metallic=0.45, roughness=0.24),
        "bulb": material("Tungsten lamp", (1.0, 0.54, 0.08, 0.72), roughness=0.08, emission=2.4),
        "lens": material("4f lens", (0.20, 0.72, 0.94, 0.34), roughness=0.06),
        "beam_splitter": material("Beam splitter", (0.54, 0.78, 1.0, 0.28), roughness=0.05),
    }

    for location, energy, size in (
        ((-420, -520, 850), 1550, 380),
        ((520, -260, 620), 1150, 310),
        ((100, 420, 760), 900, 280),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.rotation_euler = (Vector((60, 0, 330)) - light.location).to_track_quat("-Z", "Y").to_euler()

    bpy.ops.mesh.primitive_plane_add(size=1400, location=(60, 0, -1.2))
    floor = bpy.context.object
    floor.name = "matte_floor"
    floor.data.materials.append(material("Matte floor", (0.84, 0.86, 0.88, 1.0), roughness=0.80))
    return mats


def category_for(name: str, manifest_categories: dict[str, str]) -> str:
    if name in manifest_categories:
        return manifest_categories[name]
    if name.endswith("lens_A") or name.endswith("lens_B") or name.endswith("lens_C"):
        return "lens"
    if name.endswith("beam_splitter_reference"):
        return "beam_splitter"
    if name.startswith("primary_4f_") or name.startswith("secondary_4f_"):
        return "polymer_mid"
    return "polymer_mid"


def import_variant_meshes(design_dir: Path, variant: str, manifest: dict, mats: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    component_records = manifest["variants"][variant]["components"]
    categories = {record["name"]: record["category"] for record in component_records}
    mesh_dir = design_dir / "artifacts" / "render_meshes" / variant
    objects = []
    skip = {"primary_openhi_4f.stl", "secondary_openhi_4f.stl"}
    for path in sorted(mesh_dir.glob("*.stl")):
        if path.name in skip:
            continue
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = bpy.context.object
        obj.name = path.stem
        category = category_for(path.stem, categories)
        if path.stem == "tungsten_bulb":
            category = "bulb"
        elif path.stem == "qyh1123_lcd":
            category = "glass"
        elif path.stem == "lcd_lower_polarizer":
            category = "polarizer"
        obj.data.materials.append(mats[category])
        smooth = category in {"glass", "lens", "beam_splitter", "bulb", "metal", "sample"}
        for polygon in obj.data.polygons:
            polygon.use_smooth = smooth
        objects.append(obj)
    return objects


def optical_curve(name: str, points: list[list[float]], rgba, radius: float = 0.65):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 4
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for node, point in zip(spline.points, points):
        node.co = (*point, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material(f"{name} beam", rgba, roughness=0.18, emission=3.2))
    return obj


def add_optical_paths(manifest: dict, variant: str) -> list[bpy.types.Object]:
    paths = []
    for entry in manifest["variants"][variant]["optical_paths"]:
        paths.append(optical_curve(entry["name"], entry["points"], PALETTE[entry["color"]]))
    return paths


def camera(location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    cam.data.lens = 58
    cam.data.clip_end = 5000
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def render(path: Path, resolution: tuple[int, int]) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_variant(design_dir: Path, manifest: dict, variant: str, samples: int) -> None:
    mats = setup_scene(samples)
    objects = import_variant_meshes(design_dir, variant, manifest, mats)
    paths = add_optical_paths(manifest, variant)
    out = design_dir / "artifacts" / "renders"
    out.mkdir(parents=True, exist_ok=True)

    def checked_view(filename, selected, resolution, direction):
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y = resolution
        scene.render.resolution_percentage = 100
        fit, bounds = fit_camera_to_objects(selected, direction=direction)
        CAMERA_RECORDS.append({"variant": variant, "file": filename, "projected_bounds": bounds,
                               "object_count": len(selected)})
        render(out / filename, resolution)
        bpy.data.objects.remove(fit, do_unlink=True)

    full_resolution = (2200, 1700) if variant == "dual_4f" else (1800, 2400)
    checked_view(f"{variant}_nature.png", objects, full_resolution, (1.2, -1.8, 0.6))
    if variant == "single_4f":
        # The accepted close-up deliberately shows the local stack with the
        # microscope continuing out of frame. Preserve this requested detail.
        detail = out / "single_4f_lower_stack_detail.png"
        if not detail.exists():
            camera((255, -330, 205), (0, 0, 82), 230)
            render(detail, (1800, 1500))
    else:
        upper = [obj for obj in objects if obj.name.startswith(("primary_4f_", "secondary_4f_", "frame_camera", "event_camera", "c12880", "vertical_cascade"))]
        for obj in objects:
            obj.hide_render = obj not in upper
        for obj in paths:
            obj.hide_render = True
        checked_view(f"{variant}_detector_detail.png", upper, (1900, 1600), (1.2, -1.8, 0.75))


def main() -> None:
    args = parse_args()
    design_dir = args.design_dir.resolve()
    manifest = json.loads((design_dir / "artifacts" / "manifest.json").read_text())
    for variant in ("single_4f", "dual_4f", "dual_4f_vertical"):
        render_variant(design_dir, manifest, variant, args.samples)
    (design_dir / "artifacts/renders/camera_validation.json").write_text(json.dumps(CAMERA_RECORDS, indent=2) + "\n")


if __name__ == "__main__":
    main()
