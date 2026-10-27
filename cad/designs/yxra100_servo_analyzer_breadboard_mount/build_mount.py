#!/usr/bin/env python3
"""Compose supplier YXRA100 CAD and a separate breadboard/analyzer fixture."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_Cylinder

ROOT = Path(__file__).resolve().parents[3]
DESIGN = Path(__file__).resolve().parent
ART = DESIGN / "artifacts"
RUN = DESIGN / "runs/run-1-servo-full-gt090101-clearance-prototype-20261027T140000Z"
REF = ROOT / "cad/references/yixuan-yxra100"
P = {
    "breadboard_pitch": 25.0,
    "breadboard_clearance_diameter": 6.4,
    "breadboard_slot_length": 10.4,
    "foot_xmin": 68.0,
    "foot_xmax": 138.0,
    "foot_y_half": 80.0,
    "foot_thickness": 8.0,
    "wall_xmin": 68.0,
    "wall_xmax": 84.0,
    "wall_y_half": 67.0,
    "shelf_bottom": 114.0,
    "shelf_thickness": 8.0,
    "shelf_xmin": -62.0,
    "shelf_xmax": 84.0,
    "shelf_y_half": 67.0,
    "shelf_aperture_diameter": 60.0,
    "stage_bottom": 122.0,
    "stage_height": 45.0,
    "stage_aperture_diameter": 30.0,
    "adapter_diameter": 78.0,
    "adapter_thickness": 8.0,
    "adapter_clear_aperture": 30.4,
    "gt_pin_pitch": 30.0,
    "gt_pin_diameter": 5.9,
    "gt_pin_length": 16.0,
    "ear_thickness": 1.0,
    "ear_side_contact": 6.0,
    "ear_diagonal_reach": 12.0,
    "source_servo_axis_x": -42.3072444512695,
    "source_servo_axis_y": 39.8466177128033,
    "source_servo_bottom": -22.5,
}
BASE_HOLES = [(-37.5, -43.0), (37.5, -43.0), (-43.0, 50.0)]
TABLE_HOLES = [(x, y) for x in (100.0, 125.0) for y in (-50.0, 0.0, 50.0)]
ROTOR_HOLES = [(x, y) for x in (-25.0, 25.0) for y in (-12.5, 12.5)]
GT_PINS = [(x, y) for x in (-15.0, 15.0) for y in (-15.0, 15.0)]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


original = load_module("vertical_openhi_reference", ROOT / "cad/designs/openhi_vertical_multimodal_microscope_setup/build_openhi_vertical_multimodal_microscope_setup.py")
three_mf = load_module("simple_3mf", ROOT / "cad/tools/simple_3mf.py")


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0).translate(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))


def cylinder(d, z0, h, x=0.0, y=0.0):
    return cq.Workplane("XY", origin=(x, y, z0)).circle(d / 2).extrude(h)


def hex_prism(af, z0, h, x, y):
    return cq.Workplane("XY", origin=(x, y, z0)).polygon(6, af / math.cos(math.pi / 6)).extrude(h)


def fit_bounds(shape):
    b = shape.val().BoundingBox()
    return {"min": [b.xmin, b.ymin, b.zmin], "max": [b.xmax, b.ymax, b.zmax],
            "size": [b.xlen, b.ylen, b.zlen]}


def shape_volume(shape):
    return sum(s.Volume() for s in shape.solids().vals())


def ears(shape, *, base_bounds=None):
    b = shape.val().BoundingBox()
    xmin, xmax, ymin, ymax = base_bounds or (b.xmin, b.xmax, b.ymin, b.ymax)
    for x in (xmin, xmax):
        for y in (ymin, ymax):
            sx = -1 if x == xmin else 1
            sy = -1 if y == ymin else 1
            polygon = [(-6, -1), (-6, 6), (-2, 12), (9, 12), (12, 9), (12, -2), (6, -6), (-1, -6)]
            points = [(x + sx * u, y + sy * v) for u, v in polygon]
            tab = cq.Workplane("XY").polyline(points).close().extrude(P["ear_thickness"])
            shape = shape.union(tab)
    return shape.clean()


def foot():
    body = box(P["foot_xmin"], P["foot_xmax"], -80, 80, 0, 8)
    for x, y in TABLE_HOLES:
        tool = cq.Workplane("XY", origin=(x, y, -1)).slot2D(10.4, 6.4, 0).extrude(10)
        body = body.cut(tool)
    for y in (-45.0, 45.0):
        body = body.cut(cylinder(5.4, -1, 10, 76, y))
        body = body.cut(cylinder(9.8, -1, 6, 76, y))
    return body.clean()


def support():
    body = box(68, 84, -67, 67, 8, 122)
    shelf = box(-62, 84, -67, 67, 114, 122).cut(cylinder(60, 113, 10))
    body = body.union(shelf)
    for y in (-62.0, 62.0):
        # The ribs lie outside the full 110 x 70 mm sample-holder envelope.
        rib = cq.Workplane("XZ", origin=(0, y + 4, 0)).polyline([(-55, 114), (68, 22), (68, 114)]).close().extrude(8)
        body = body.union(rib)
    for x, y in BASE_HOLES:
        body = body.cut(cylinder(6.6, 113, 10, x, y))
        body = body.cut(hex_prism(10.4, 113, 6, x, y))
    for y in (-45.0, 45.0):
        body = body.cut(cylinder(5.4, 7, 22, 76, y))
        body = body.cut(hex_prism(8.4, 18, 4.3, 76, y))
        body = body.cut(box(67, 76, y - 4.2, y + 4.2, 18, 22.3))
    return body.clean()


def analyzer_adapter():
    body = cylinder(78, 0, 8).cut(cylinder(30.4, -1, 10))
    for x, y in ROTOR_HOLES:
        body = body.cut(cylinder(6.4, -1, 10, x, y))
        body = body.cut(cylinder(11, 3.5, 5.5, x, y))
    for x, y in GT_PINS:
        body = body.union(cylinder(5.9, 8, 16, x, y))
    return body.clean()


def stage_transform(shape):
    normalized = shape.translate((-P["source_servo_axis_x"], -P["source_servo_axis_y"], -P["source_servo_bottom"]))
    return normalized.rotate((0, 0, 0), (0, 0, 1), 90).translate((0, 0, P["stage_bottom"]))


def measure_base_holes(source):
    centers = set()
    for f in source.solids().vals()[0].Faces():
        a = BRepAdaptor_Surface(f.wrapped)
        if a.GetType() != GeomAbs_Cylinder:
            continue
        c = a.Cylinder()
        if abs(c.Radius() - 3.25) < 1e-5 and abs(c.Axis().Direction().Z()) > 0.99:
            x, y, _ = c.Location().Coord()
            centers.add((round(-(y - P["source_servo_axis_y"]), 4), round(x - P["source_servo_axis_x"], 4)))
    return sorted(centers)


def intersection_volume(a, b):
    return shape_volume(a.intersect(b))


def export_part(name, shape):
    cq.exporters.export(shape, str(ART / f"{name}.step"))
    cq.exporters.export(shape, str(ART / f"{name}.stl"), tolerance=0.035, angularTolerance=0.08)
    back = cq.importers.importStep(str(ART / f"{name}.step"))
    if not BRepCheck_Analyzer(back.val().wrapped).IsValid():
        raise RuntimeError(f"Invalid STEP: {name}")
    return {"bounds_mm": fit_bounds(back), "solids": len(back.val().Solids()), "volume_mm3": shape_volume(back)}


def export_print(name, shape):
    b = shape.val().BoundingBox()
    # OCCT's conservative spline bounds can extend below a perfectly planar
    # base. Ground the real vertices instead of that padded box.
    base_z = min(vertex.Z for vertex in shape.val().Vertices())
    grounded = shape.translate((-(b.xmin + b.xmax) / 2, -(b.ymin + b.ymax) / 2, -base_z))
    stem = "PRINT_THIS_" + name
    record = export_part(stem, grounded)
    mesh = trimesh.load_mesh(ART / f"{stem}.stl", force="mesh")
    first_layer = bool(np.any(np.min(mesh.triangles[:, :, 2], axis=1) <= 0.2))
    if not mesh.is_watertight or len(mesh.split()) != 1 or abs(float(mesh.bounds[0, 2])) > 1e-5 or not first_layer:
        raise RuntimeError(f"Bad direct print: {name}")
    three_mf.export_stl_as_3mf(ART / f"{stem}.stl", ART / f"{stem}.3mf", title=name)
    with zipfile.ZipFile(ART / f"{stem}.3mf") as archive:
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        if len(root.findall("m:build/m:item", ns)) != 1:
            raise RuntimeError("A direct print must have exactly one build item")
    for suffix in ("step", "stl", "3mf"):
        shutil.copy2(ART / f"{stem}.{suffix}", RUN / f"{stem}.{suffix}")
    record.update({"watertight": True, "mesh_components": 1, "min_z_mm": float(mesh.bounds[0, 2]),
                   "first_layer_nonempty": first_layer, "three_mf_build_items": 1, "stem": stem})
    return record


def main(*, extra_components=None, extra_prints=None, extra_manifest=None):
    ART.mkdir(exist_ok=True, parents=True)
    RUN.mkdir(exist_ok=True, parents=True)
    source = cq.importers.importStep(str(REF / "YXRA100_100W_servo.step"))
    actual_holes = measure_base_holes(source)
    if actual_holes != sorted(BASE_HOLES):
        raise RuntimeError(f"Supplier mounting holes differ: {actual_holes}")
    stationary = stage_transform(cq.Workplane(obj=source.solids().vals()[0]))
    # Preserve all vendor entities, including the motor's open surface shells.
    vendor_stage = stage_transform(source)
    support_body, foot_body, adapter_body = support(), foot(), analyzer_adapter()
    rotor_top = P["stage_bottom"] + P["stage_height"]
    installed_adapter = adapter_body.translate((0, 0, rotor_top))
    gt_source = cq.importers.importStep(str(original.SOURCE["gt090101"]))
    gt_bottom = rotor_top + P["adapter_thickness"]
    gt = gt_source.translate((0, 0, gt_bottom - gt_source.val().BoundingBox().zmin))

    old_components, _ = original.build_variant("single_4f")
    lower_names = {"dock", "sample_holder_and_cap", "lamp_holder", "lamp_pcb", "lcd_holder", "qyh1123_lcd",
                   "lcd_lower_polarizer", "petri_dish", "sample_volume", "tungsten_bulb", "tungsten_bulb_leads"}
    lower = [part for part in old_components if part.name in lower_names or part.name.startswith("spacer_") or part.name.endswith("_lower")]
    old_gt_top = original.P["gt090101_top_z_mm"]
    new_gt_top = gt_bottom + gt_source.val().BoundingBox().zlen
    microscope_lift = new_gt_top - old_gt_top
    microscope = next(part.shape for part in old_components if part.name == "openhi_microscope").translate((0, 0, microscope_lift))
    instrument_adapter = cylinder(30, new_gt_top, 8).cut(cylinder(24, new_gt_top - 1, 10))

    components = [("breadboard_foot", foot_body, (0.16, 0.34, 0.42)),
                  ("gusseted_L_support", support_body, (0.20, 0.43, 0.51)),
                  ("YXRA100_servo_vendor", vendor_stage, (0.10, 0.11, 0.13)),
                  ("rotating_analyzer_adapter", installed_adapter, (0.85, 0.56, 0.16)),
                  ("GT090101_analyzer", gt, (0.12, 0.13, 0.15))]
    for part in lower:
        color = (0.58, 0.62, 0.66) if "rod" in part.name or "spacer" in part.name else (0.24, 0.26, 0.29)
        if "pcb" in part.name:
            color = (0.05, 0.36, 0.18)
        if "sample" == part.name or part.name in ("petri_dish", "sample_volume"):
            color = (0.12, 0.66, 0.65)
        components.append((part.name, part.shape, color))
    components.extend([("openhi_microscope_relocated", microscope, (0.57, 0.60, 0.63)),
                       ("GT_to_microscope_proxy", instrument_adapter, (0.35, 0.38, 0.41))])
    for part in old_components:
        if part.name in {"primary_openhi_4f", "microscope_to_4f_adapter"} or part.name.startswith(("frame_camera_", "c12880_")):
            color = (0.22, 0.25, 0.28)
            if part.name == "frame_camera_body":
                color = (0.12, 0.32, 0.48)
            elif part.name == "c12880_board":
                color = (0.04, 0.40, 0.22)
            components.append((part.name, part.shape.translate((0, 0, microscope_lift)), color))
    components.extend(extra_components or [])

    validation = {}
    for name, body in (("breadboard_foot", foot_body), ("gusseted_L_support", support_body),
                       ("rotating_analyzer_adapter", adapter_body), ("vendor_YXRA100_servo_positioned", vendor_stage)):
        validation[name] = export_part(name, body)
    for name, shape, _ in extra_components or []:
        validation[name] = export_part(name, shape)
    assembly = cq.Assembly(name="YXRA100_servo_GT090101_analyzer_integration")
    render_records = []
    for name, shape, color in components:
        assembly.add(shape, name=name, color=cq.Color(*color))
        cq.exporters.export(shape, str(ART / f"scene_{name}.stl"), tolerance=0.07, angularTolerance=0.15)
        render_records.append({"name": name, "mesh": f"scene_{name}.stl", "color": color})
    assembly_path = ART / "yxra100_servo_analyzer_breadboard_mount_assembly.step"
    assembly.save(str(assembly_path))
    back = cq.importers.importStep(str(assembly_path))
    if not BRepCheck_Analyzer(back.val().wrapped).IsValid():
        raise RuntimeError("Assembly STEP round trip invalid")
    shutil.copy2(assembly_path, DESIGN / "USE_THIS_yxra100_servo_analyzer_breadboard_mount_assembly.step")
    clean_stand_print = support_body.rotate((0, 0, 0), (0, 1, 0), 90)
    bb = clean_stand_print.val().BoundingBox()
    clean_stand_print = clean_stand_print.translate((0, 0, -bb.zmin))
    print_records = {
        "breadboard_foot": export_print("yxra100_breadboard_foot_with_ears", ears(foot_body)),
        "L_support": export_print("yxra100_L_support_on_back_with_ears", ears(clean_stand_print)),
        "GT_adapter": export_print("yxra100_full_GT090101_rotating_adapter", adapter_body),
    }
    for key, (name, shape) in (extra_prints or {}).items():
        print_records[key] = export_print(name, shape)
    interactions = {}
    for name, hardware in (("stationary_stage", stationary), ("dock", next(p.shape for p in lower if p.name == "dock")),
                           ("sample_holder", next(p.shape for p in lower if p.name == "sample_holder_and_cap"))):
        interactions[name] = intersection_volume(support_body, hardware) + intersection_volume(foot_body, hardware)
    rotor = stage_transform(cq.Workplane(obj=source.solids().vals()[3]))
    interactions["rotor_vs_support"] = intersection_volume(support_body, rotor)
    interactions["GT_vs_adapter"] = intersection_volume(installed_adapter, gt)
    # The complete GT frame and adapter rotate together around the optical Z axis.
    sweep_interference = []
    for angle in range(0, 360, 15):
        swept = installed_adapter.rotate((0, 0, 0), (0, 0, 1), angle)
        swept_gt = gt.rotate((0, 0, 0), (0, 0, 1), angle)
        sweep_interference.append(intersection_volume(swept, stationary) + intersection_volume(swept_gt, stationary))
    if any(v > 0.01 for v in interactions.values()) or max(sweep_interference) > 0.01:
        raise RuntimeError(f"Unwanted overlap: {interactions}; sweep {max(sweep_interference)}")
    source_files = {"servo_stage": REF / "YXRA100_100W_servo.step", "drawing": REF / "YXRA100_40_servo_specification.pdf",
                    "GT090101": original.SOURCE["gt090101"], "sample_holder": original.SOURCE["sample_holder"]}
    manifest = {
        "design": DESIGN.name, "run_name": RUN.name,
        "status": "measured mechanical integration prototype; optical working distance and load test still required",
        "selected_motor": "40 mm / 100 W servo", "analyzer": "complete GT090101 mount",
        "parameters_mm": P, "stationary_base_holes_mm": BASE_HOLES, "measured_source_holes_mm": actual_holes,
        "breadboard_holes_mm": TABLE_HOLES, "rotor_attachment_holes_mm": ROTOR_HOLES,
        "cage_pin_centers_mm": GT_PINS, "geometry_validation": validation, "print_validation": print_records,
        "interference_volume_mm3": interactions, "rotating_assembly_max_interference_mm3_15deg_samples": max(sweep_interference),
        "assembly_step_round_trip_valid": True, "render_components": render_records,
        "sources": {k: {"path": str(v.relative_to(ROOT)), "sha256": hashlib.sha256(v.read_bytes()).hexdigest()} for k, v in source_files.items()},
        "source_transform": "translate optical center to XY origin and underside to Z=0; rotate +90 deg about Z; translate Z=122 mm",
        "vendor_topology": {"solids": len(source.val().Solids()), "shells": len(source.val().Shells()),
                            "note": "The servo motor includes open vendor surface shells. They are preserved, not silently discarded or claimed printable."},
        "optical_constraints": {"sample_holder_top_z_mm": 109.0, "shelf_bottom_z_mm": 114.0,
                                "vertical_gap_mm": 5.0, "stage_top_z_mm": rotor_top, "GT_bottom_z_mm": gt_bottom,
                                "GT_top_z_mm": new_gt_top, "required_microscope_upshift_mm": microscope_lift,
                                "focus_validated": False,
                                "note": "Raising the microscope is only a collision-free integration layout, not proof of preserved sample focus. Verify objective working distance before printing the large support."},
        "remote_context": {"requested_host": "CSG1175-P", "read_success": False,
                           "reason": "Native UU terminal refused because another controller owns the device; no takeover performed."},
        "hardware": ["6x M6 breadboard screws and washers; use lengths suitable for the actual table",
                     "2x M5 x 20 socket screws and M5 nuts for foot-to-support joint",
                     "3x M6 x 25 socket screws and M6 nuts for stationary stage base",
                     "4x M6 x 10 low-head screws, head height <=4.5 mm, for rotating adapter",
                     "GT090101 side-lock screws clamp the four 5.9 mm printed locating pins; do not retain any rods joining it to the stationary sample stage"],
        "limitations": ["No stage motion or electrical control was performed.",
                        "The support is a fit/clearance prototype, not a structural or thermal load certification.",
                        "Use rigid metal for final metrology support; printed polymer can creep under the roughly 1.85 kg stage.",
                        "Cable bend radius, live specimen access, screw lengths and microscope working distance need physical verification.",
                        "The 25 mm breadboard grid is a metric-board assumption, not a measurement of this particular table."]
    }
    manifest.update(extra_manifest or {})
    (ART / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in (assembly_path, ART / "manifest.json"):
        shutil.copy2(path, RUN / path.name)
    print(json.dumps({"assembly": str(assembly_path), "checks": interactions, "microscope_lift_mm": microscope_lift,
                      "print_validation": print_records}, indent=2), flush=True)
    return manifest, components


if __name__ == "__main__":
    main()
