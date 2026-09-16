#!/usr/bin/env python3
"""Paper-figure renders of the EVK 5 holder aligned on the incubator light path.

Run:  blender --background --python <this file> -- [--design-dir DIR] [--samples N] [--scale S]

Outputs artifacts/paper_figure/<name>.png (white) and <name>_transparent.png, plus
<name>_labels.json with 2D anchor pixels for the labelled composite made by
compose_paper_figure_labels.py.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

# publication palette (RGBA, linear)
PAL = {
    "holder_moved": (0.85, 0.33, 0.06, 1.0),
    "sensor_plate": (0.06, 0.30, 0.14, 1.0),
    "grating": (0.08, 0.20, 0.52, 1.0),
    "walls": (0.55, 0.58, 0.62, 0.16),
    "lower_shelf": (0.36, 0.38, 0.41, 1.0),
    "upper_shelf": (0.36, 0.38, 0.41, 0.30),
    "stage": (0.20, 0.21, 0.23, 1.0),
    "rest": (0.30, 0.31, 0.33, 1.0),
    "slider": (0.13, 0.14, 0.16, 1.0),
    "led_holder": (0.85, 0.33, 0.06, 1.0),
    "lumileds_pcb": (0.05, 0.28, 0.12, 1.0),
    "lumileds_pcb_parts": (0.75, 0.75, 0.72, 1.0),
    "lumileds_led": (1.0, 0.95, 0.70, 1.0),
}
AXIS_RGBA = (1.0, 0.72, 0.05, 1.0)
AXIS_XY = None  # filled from manifest


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--design-dir", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=float, default=1.0, help="resolution multiplier (1.0 = 2400x1800)")
    return ap.parse_args(argv)


def clear() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def make_material(name: str, rgba, emission: float = 0.0, roughness: float = 0.5) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = 0.3 if "Specular IOR Level" in bsdf.inputs else 0.3
    if rgba[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = rgba[3]
        mat.blend_method = "HASHED"
        mat.shadow_method = "NONE"
        mat.use_backface_culling = True
    if emission > 0:
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = rgba
    return mat


def import_stl(path: Path, name: str, rgba) -> bpy.types.Object | None:
    if not path.exists():
        return None
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.name = name
    for poly in obj.data.polygons:
        poly.use_smooth = False
    obj.data.materials.append(make_material(name, rgba))
    return obj


def bounds(objs) -> tuple[Vector, Vector]:
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def add_axis(x: float, y: float, z0: float, z1: float, radius: float = 0.9) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=z1 - z0, location=(x, y, (z0 + z1) / 2), vertices=32)
    ax = bpy.context.object
    ax.name = "light_path"
    ax.data.materials.append(make_material("light_path", AXIS_RGBA, emission=4.0, roughness=0.9))
    return ax


def add_light_cone(x: float, y: float, z_top: float, z_bottom: float, r_top: float, r_bottom: float) -> bpy.types.Object:
    """Soft translucent beam to suggest the illumination cone (figure aid only)."""
    bpy.ops.mesh.primitive_cone_add(radius1=r_bottom, radius2=r_top, depth=z_top - z_bottom, location=(x, y, (z_top + z_bottom) / 2), vertices=48)
    cone = bpy.context.object
    cone.name = "light_beam"
    cone.data.materials.append(make_material("light_beam", (1.0, 0.80, 0.25, 0.12), emission=0.6))
    return cone


def camera(location: Vector, target: Vector, *, ortho: float | None = None, lens: float = 50.0) -> bpy.types.Object:
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.lens = lens
    cam.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = 20000
    bpy.context.scene.camera = cam
    return cam


def setup(samples: int, scale: float) -> None:
    sc = bpy.context.scene
    sc.render.resolution_x = int(2400 * scale)
    sc.render.resolution_y = int(1800 * scale)
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.compression = 40
    try:
        sc.render.engine = "BLENDER_EEVEE"
    except Exception:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    ev = sc.eevee
    ev.taa_render_samples = samples
    for attr, val in (("use_gtao", True), ("gtao_distance", 40.0), ("use_soft_shadows", True), ("shadow_cube_size", "2048"),
                      ("shadow_cascade_size", "4096"), ("use_shadow_high_bitdepth", True), ("use_ssr", False)):
        try:
            setattr(ev, attr, val)
        except Exception:
            pass
    sc.view_settings.view_transform = "Filmic"
    sc.view_settings.look = "Medium Contrast"
    sc.view_settings.exposure = -0.25
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs[1].default_value = 0.55
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 2000))
    sun = bpy.context.object
    sun.data.energy = 2.0
    sun.data.angle = math.radians(6)
    sun.rotation_euler = (math.radians(38), math.radians(-18), math.radians(35))
    bpy.ops.object.light_add(type="AREA", location=(-500, -900, 900))
    fill = bpy.context.object
    fill.data.energy = 9e5
    fill.data.size = 900
    fill.rotation_euler = (Vector((141, 143, 200)) - fill.location).to_track_quat("-Z", "Y").to_euler()


def render(path: Path, transparent_twin: bool = True) -> None:
    """Render with a transparent film; compose_paper_figure_labels.py makes the white and labelled versions."""
    sc = bpy.context.scene
    sc.render.film_transparent = True
    sc.render.filepath = str(path.with_name(path.stem + "_transparent.png"))
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath)


def anchors_json(path: Path, cam: bpy.types.Object, points: dict[str, Vector]) -> None:
    sc = bpy.context.scene
    out = {}
    for name, p in points.items():
        v = world_to_camera_view(sc, cam, p)
        out[name] = {"x_px": v.x * sc.render.resolution_x, "y_px": (1.0 - v.y) * sc.render.resolution_y, "world": list(p)}
    path.write_text(json.dumps(out, indent=1))


def section_cut(objs, y_cut: float, keep_positive: bool) -> None:
    """Remove the half y < y_cut (or > y_cut) with a boolean cutter so the axis plane is exposed."""
    size = 5000.0
    off = -size / 2 if keep_positive else size / 2
    bpy.ops.mesh.primitive_cube_add(size=size, location=(141.25, y_cut + off, 200))
    cutter = bpy.context.object
    cutter.name = "section_cutter"
    cutter.hide_render = True
    cutter.hide_viewport = True
    for o in objs:
        mod = o.modifiers.new("section", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        mod.solver = "FAST"


def main() -> None:
    args = parse_args()
    dd = args.design_dir
    manifest = json.loads((dd / "artifacts" / "manifest.json").read_text())
    ax_xy = manifest["optical_axis_xy_mm"]["from_sensor_plate_centre"]
    plate_top = manifest["sensor_plate"]["top_z"]
    grating_top = manifest["grating"]["bbox"]["zmax"]
    holder_bb = manifest["holder_group"]["bbox_after"]
    meshes = dd / "artifacts" / "render_meshes"
    out = dd / "artifacts" / "paper_figure"
    out.mkdir(parents=True, exist_ok=True)

    clear()
    setup(args.samples, args.scale)
    objs = {k: import_stl(meshes / f"{k}.stl", k, v) for k, v in PAL.items()}
    objs = {k: v for k, v in objs.items() if v}
    for k in ("slider", "led_holder", "lumileds_pcb", "lumileds_pcb_parts", "lumileds_led"):
        if k in objs:
            objs[k].hide_render = True
    lo, hi = bounds([v for k, v in objs.items() if k not in ("slider", "led_holder", "lumileds_pcb", "lumileds_pcb_parts", "lumileds_led")])
    lid_top = hi.z
    axis = add_axis(ax_xy[0], ax_xy[1], holder_bb["zmax"] - 8.0, lid_top + 25.0)
    beam = add_light_cone(ax_xy[0], ax_xy[1], grating_top + 60.0, holder_bb["zmax"] + 0.5, 4.0, 6.0)
    beam.hide_render = True
    centre_box = (lo + hi) / 2
    size = max(hi - lo)
    holder_c = Vector(((holder_bb["xmin"] + holder_bb["xmax"]) / 2, (holder_bb["ymin"] + holder_bb["ymax"]) / 2, (holder_bb["zmin"] + holder_bb["zmax"]) / 2))
    gb = manifest["grating"]["bbox"]
    grating_c = Vector(((gb["xmin"] + gb["xmax"]) / 2, (gb["ymin"] + gb["ymax"]) / 2, (gb["zmin"] + gb["zmax"]) / 2))
    pb = manifest["sensor_plate"]["bbox"]
    plate_edge = Vector((pb["xmax"] - 25.0, pb["ymin"] + 12.0, plate_top))
    prop = manifest.get("figure_proposal", {})
    slider_c = Vector((ax_xy[0], ax_xy[1], (prop.get("rail_bottom_z", 300) + prop.get("carriage_bottom_z", 290)) / 2)) if prop else None
    led_c = Vector((ax_xy[0], ax_xy[1], prop.get("board_component_face_z", 283))) if prop else None
    holder_led_c = Vector((ax_xy[0] + 18.0, ax_xy[1] - 18.0, sum(prop.get("holder_z", [282, 290])) / 2)) if prop else None
    anchors = {"holder": holder_c,
               "slider": slider_c if slider_c else holder_c,
               "lumileds_pcb": led_c if led_c else holder_c,
               "led_holder": holder_led_c if holder_led_c else holder_c,
               "holder_top": Vector((holder_c.x + 12.0, holder_c.y - 14.0, holder_bb["zmax"])),
               "grating": grating_c,
               "grating_edge": Vector((gb["xmin"] + 8.0, gb["ymin"] + 8.0, gb["zmax"])),
               "sensor_board": plate_edge,
               "sensor_board_left": Vector((pb["xmin"] + 20.0, ax_xy[1], plate_top)),
               "sensor_board_right": Vector((pb["xmax"] - 20.0, ax_xy[1], plate_top)),
               "light_path": Vector((ax_xy[0], ax_xy[1], grating_top + 55.0)),
               "light_path_low": Vector((ax_xy[0], ax_xy[1], grating_top + 22.0)),
               "light_path_high": Vector((ax_xy[0], ax_xy[1], grating_top + 110.0)),
               "upper_shelf_window": Vector((ax_xy[0] + 48.0, ax_xy[1] + 48.0, 187.3)),
               "upper_shelf_window_right": Vector((ax_xy[0] + 52.0, ax_xy[1], 185.3)),
               "incubator": Vector((lo.x + 5.0, lo.y + 120.0, lo.z + 150.0))}

    # Fig A: full incubator, front open, walls translucent, iso from front-left above
    cam = camera(centre_box + Vector((-1.25, -1.75, 0.95)) * size, centre_box + Vector((0, 0, -15)), lens=50)
    render(out / "figA_incubator_overview.png")
    anchors_json(out / "figA_incubator_overview_labels.json", cam, anchors)
    bpy.data.objects.remove(cam)

    # Fig A2: same view, clean: no rails, no axis line, with the proposed stage slider + Lumileds PCB
    for k in ("slider", "led_holder", "lumileds_pcb", "lumileds_pcb_parts", "lumileds_led"):
        if k in objs:
            objs[k].hide_render = False
    if "rest" in objs:
        objs["rest"].hide_render = True
    axis.hide_render = True
    cam = camera(centre_box + Vector((-1.25, -1.75, 0.95)) * size, centre_box + Vector((0, 0, -15)), lens=50)
    render(out / "figA2_incubator_overview_clean_slider.png")
    anchors_json(out / "figA2_incubator_overview_clean_slider_labels.json", cam, anchors)
    bpy.data.objects.remove(cam)
    axis.hide_render = False
    if "rest" in objs:
        objs["rest"].hide_render = False
    for k in ("slider", "led_holder", "lumileds_pcb", "lumileds_pcb_parts", "lumileds_led"):
        if k in objs:
            objs[k].hide_render = True

    # Fig F: front elevation (orthographic from -Y): slider, LED holder, grating window, EVK 5 holder on one vertical line
    for k in ("slider", "led_holder", "lumileds_pcb", "lumileds_pcb_parts", "lumileds_led"):
        if k in objs:
            objs[k].hide_render = False
    if "rest" in objs:
        objs["rest"].hide_render = True
    axis.hide_render = True
    zc = (plate_top + prop.get("rail_bottom_z", 300)) / 2
    cam = camera(Vector((ax_xy[0], ax_xy[1] - 1500, zc)), Vector((ax_xy[0], ax_xy[1], zc)), ortho=(hi.x - lo.x) * 1.08)
    render(out / "figF_front_elevation_alignment.png")
    anchors_json(out / "figF_front_elevation_alignment_labels.json", cam, anchors)
    bpy.data.objects.remove(cam)
    axis.hide_render = False
    if "rest" in objs:
        objs["rest"].hide_render = False
    for k in ("slider", "led_holder", "lumileds_pcb", "lumileds_pcb_parts", "lumileds_led"):
        if k in objs:
            objs[k].hide_render = True

    # Fig B: optical stack only (no walls/stage/rest), low iso
    for k in ("walls", "stage", "rest"):
        if k in objs:
            objs[k].hide_render = True
    stack = [objs[k] for k in ("holder_moved", "sensor_plate", "grating", "upper_shelf", "lower_shelf") if k in objs]
    lo2, hi2 = bounds(stack)
    c2 = (lo2 + hi2) / 2
    s2 = max(hi2 - lo2)
    cam = camera(c2 + Vector((-0.95, -1.25, 0.62)) * s2, c2 + Vector((0, 0, -5)), lens=60)
    render(out / "figB_optical_stack.png")
    anchors_json(out / "figB_optical_stack_labels.json", cam, anchors)
    bpy.data.objects.remove(cam)

    # Fig C: close-up of holder on sensor board under the grating window, upper shelf hidden
    objs["upper_shelf"].hide_render = True
    objs["lower_shelf"].hide_render = True
    close = [objs["holder_moved"], objs["grating"]]
    lo3, hi3 = bounds(close)
    c3 = (lo3 + hi3) / 2
    s3 = max(hi3 - lo3)
    cam = camera(c3 + Vector((-1.35, -2.0, 0.85)) * s3, c3 + Vector((0, 0, -8)), lens=55)
    render(out / "figC_holder_under_grating_closeup.png")
    anchors_json(out / "figC_holder_under_grating_closeup_labels.json", cam, anchors)
    bpy.data.objects.remove(cam)

    # Fig D: orthographic top view through the grating window (grating hidden), shows centring
    objs["grating"].hide_render = True
    lo4, hi4 = bounds([objs["holder_moved"]])
    span = max(hi4.x - lo4.x, hi4.y - lo4.y) * 1.9
    cam = camera(Vector((ax_xy[0], ax_xy[1], 900)), Vector((ax_xy[0], ax_xy[1], plate_top)), ortho=span)
    cam.rotation_euler = (0, 0, 0)
    render(out / "figD_top_view_centred.png")
    anchors_json(out / "figD_top_view_centred_labels.json", cam, anchors)
    bpy.data.objects.remove(cam)
    objs["grating"].hide_render = False
    beam.hide_render = False

    # Fig E: section through the optical axis (front half removed), orthographic elevation
    for k in ("upper_shelf", "lower_shelf", "walls"):
        if k in objs:
            objs[k].hide_render = False
    if "stage" in objs:
        objs["stage"].hide_render = False
    section_cut([o for k, o in objs.items()], ax_xy[1], keep_positive=True)
    lo5, hi5 = bounds([objs[k] for k in ("holder_moved", "sensor_plate", "grating", "lower_shelf", "upper_shelf", "walls") if k in objs])
    c5 = Vector((ax_xy[0], ax_xy[1], (plate_top - 45 + grating_top + 60) / 2))
    cam = camera(Vector((ax_xy[0], ax_xy[1] - 1500, c5.z)), c5, ortho=(hi5.x - lo5.x) * 1.1)
    render(out / "figE_section_through_light_path.png")
    anchors_json(out / "figE_section_through_light_path_labels.json", cam, anchors)
    bpy.data.objects.remove(cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "paper_figure_scene.blend"))


if __name__ == "__main__":
    main()
