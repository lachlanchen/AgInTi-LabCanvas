#!/usr/bin/env python3
"""Preserve the exact QYH1123 baseline and rotate only its LCD features."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import cadquery as cq
import trimesh
from OCP.BRepTools import BRepTools

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
ART = DESIGN / "artifacts"
STEM = "qyh1123_light_valve_centered_clearance_cage_holder"
STAMP = "20261028T053648Z"
RUNS = {
    "0deg": DESIGN / "runs" / f"run-1-exact-tolerance-adjusted-original-print-ready-{STAMP}",
    "45deg": DESIGN / "runs" / f"run-2-lcd-seat-45deg-print-ready-{STAMP}",
}
SOURCE_SCRIPT = DESIGN / f"build_{STEM}.py"
spec = importlib.util.spec_from_file_location("qyh1123_accepted_baseline", SOURCE_SCRIPT)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
sys.path.insert(0, str(ROOT / "cad/tools"))
from simple_3mf import export_stl_as_3mf


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def volume(shape):
    return sum(s.Volume(1e-8) for s in shape.solids().vals())


def valid(shape):
    BRepTools.Clean_s(shape.val().wrapped)
    return shape.val().isValid()


def changed_volume(a, b):
    return volume(a.cut(b)) + volume(b.cut(a))


def blank_and_cuts():
    p = baseline.PARAMS
    h = p["body_thickness_mm"]
    body = cq.Workplane("XY").box(p["body_width_mm"], p["body_height_mm"], h)
    body = body.edges("|Z").fillet(p["edge_fillet_mm"])
    for x in (-15, 15):
        for y in (-15, 15):
            body = body.cut(baseline.z_cylinder(p["cage_rod_clearance_diameter_mm"], h + 1.2, -h / 2 - 0.6).translate((x, y, 0)))
    window_w, window_h = baseline.light_window_xy()
    cuts = baseline.z_box((window_w, window_h, h + 1.2), (0, 0, 0))
    depth = p["valve_pocket_depth_mm"]
    cuts = cuts.union(baseline.z_box(
        (p["valve_outer_width_mm"] + p["valve_pocket_clearance_mm"],
         p["valve_outer_height_mm"] + p["valve_pocket_clearance_mm"], depth + 0.1),
        (0, 0, h / 2 - depth / 2 + 0.04)))
    bottom_y = -(p["valve_outer_height_mm"] + p["valve_pocket_clearance_mm"]) / 2
    length = p["body_height_mm"] / 2 + bottom_y + 0.35
    relief_depth = p["pin_exit_relief_depth_mm"]
    cuts = cuts.union(baseline.z_box((p["pin_exit_relief_width_mm"], length, relief_depth),
                                   (0, bottom_y - length / 2 + 0.02, h / 2 - relief_depth / 2 + 0.04)))
    return body, cuts


def export_print(shape, run, key):
    # Exact geometry request: no new ears or extra features; back face down.
    printable = shape.translate((0, 0, baseline.PARAMS["body_thickness_mm"] / 2))
    stem = f"PRINT_THIS_qyh1123_holder_{key}"
    cq.exporters.export(printable, str(run / (stem + ".step")))
    cq.exporters.export(printable, str(run / (stem + ".stl")), tolerance=0.02, angularTolerance=0.10)
    export_stl_as_3mf(run / (stem + ".stl"), run / (stem + ".3mf"), title=stem)
    back = cq.importers.importStep(str(run / (stem + ".step")))
    mesh = trimesh.load_mesh(run / (stem + ".stl"), force="mesh")
    first_layer = mesh.section(plane_origin=(0, 0, 0.2), plane_normal=(0, 0, 1)) is not None
    with zipfile.ZipFile(run / (stem + ".3mf")) as archive:
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    count = len(model.findall("m:build/m:item", ns))
    checks = {"stem": stem, "solid_count": len(back.solids().vals()), "step_valid": valid(back),
              "watertight": mesh.is_watertight, "mesh_components": len(mesh.split(only_watertight=False)),
              "min_z_mm": float(mesh.bounds[0, 2]), "first_layer_nonempty": first_layer,
              "three_mf_build_items": count, "three_mf_units": model.attrib["unit"],
              "ears_added": False, "orientation": "unchanged XY, flat back at Z=0"}
    if not (checks["solid_count"] == 1 and checks["step_valid"] and checks["watertight"]
            and checks["mesh_components"] == 1 and abs(checks["min_z_mm"]) < 1e-6
            and first_layer and count == 1 and checks["three_mf_units"] == "millimeter"):
        raise RuntimeError(f"Invalid print package: {checks}")
    return checks


def main():
    source_files = {"holder_step": ART / f"{STEM}.step", "holder_stl": ART / f"{STEM}.stl",
                    "assembly_step": ART / f"{STEM}_assembly.step", "assembly_stl": ART / f"{STEM}_assembly.stl",
                    "valve_step": ART / f"{STEM}_valve_proxy.step", "valve_stl": ART / f"{STEM}_valve_proxy.stl",
                    "rods_step": ART / f"{STEM}_cage_rods_proxy.step", "rods_stl": ART / f"{STEM}_cage_rods_proxy.stl",
                    "parameters": ART / "manifest.json", "source_script": SOURCE_SCRIPT}
    hashes = {key: sha(path) for key, path in source_files.items()}
    original = cq.importers.importStep(str(source_files["holder_step"]))
    body, cutters = blank_and_cuts()
    zero_diff = changed_volume(original, body.cut(cutters))
    if zero_diff > 1e-5:
        raise RuntimeError(f"Baseline reconstruction differs from accepted STEP: {zero_diff}")
    rods = cq.importers.importStep(str(source_files["rods_step"]))
    valve0 = cq.importers.importStep(str(source_files["valve_step"]))
    variants = {}
    for key, angle in (("0deg", 0), ("45deg", 45)):
        run = RUNS[key]
        run.mkdir(parents=True, exist_ok=True)
        holder = original if angle == 0 else body.cut(cutters.rotate((0, 0, 0), (0, 0, 1), angle))
        valve = valve0 if angle == 0 else valve0.rotate((0, 0, 0), (0, 0, 1), angle)
        if angle == 0:
            for source_key, filename in (("holder_step", "holder.step"), ("holder_stl", "holder.stl"),
                                         ("assembly_step", "qyh1123_holder_0deg_assembly.step"),
                                         ("assembly_stl", "assembly.stl"),
                                         ("valve_step", "valve_proxy.step"), ("valve_stl", "valve_proxy.stl")):
                shutil.copy2(source_files[source_key], run / filename)
        else:
            for name, shape in (("holder", holder), ("valve_proxy", valve)):
                for suffix in ("step", "stl"):
                    cq.exporters.export(shape, str(run / f"{name}.{suffix}"))
            assembly = cq.Assembly(name="QYH1123_45deg_LCD_seat_fixed_cage")
            for name, shape, color in (("holder", holder, (0.22, 0.28, 0.31)),
                                       ("LCD_and_pins_reference", valve, (0.25, 0.7, 0.8)),
                                       ("unchanged_cage_rods_reference", rods, (0.65, 0.7, 0.75))):
                assembly.add(shape, name=name, color=cq.Color(*color))
            assembly.save(str(run / "qyh1123_holder_45deg_assembly.step"))
            cq.exporters.export(assembly.toCompound(), str(run / "assembly.stl"))
        for suffix in ("step", "stl"):
            shutil.copy2(source_files["rods_" + suffix], run / ("rods_proxy." + suffix))
        assembly_path = run / f"qyh1123_holder_{key}_assembly.step"
        assembly_back = cq.importers.importStep(str(assembly_path))
        back = cq.importers.importStep(str(run / "holder.step"))
        checks = {"holder_valid": valid(back), "holder_solid_count": len(back.solids().vals()),
                  "assembly_valid": valid(assembly_back), "holder_valve_overlap_mm3": volume(holder.intersect(valve)),
                  "valve_rods_overlap_mm3": volume(valve.intersect(rods)),
                  "round_trip_changed_volume_mm3": changed_volume(holder, back),
                  "baseline_reconstruction_changed_volume_mm3": zero_diff,
                  "rod_probe_overlap_mm3": 0.0}
        for x in (-15, 15):
            for y in (-15, 15):
                probe = baseline.z_cylinder(6.3, 9, -4.5).translate((x, y, 0))
                checks["rod_probe_overlap_mm3"] += volume(holder.intersect(probe))
        if not (checks["holder_valid"] and checks["assembly_valid"] and checks["holder_solid_count"] == 1
                and all(value < 1e-5 for name, value in checks.items() if name.endswith("_mm3"))):
            raise RuntimeError(f"Invalid geometry: {key}: {checks}")
        printed = export_print(holder, run, key)
        data = {"design": STEM, "variant": key, "run_name": run.name, "seat_rotation_deg": angle,
                "rotation_rule": "Rotate LCD pocket, through-window, pin relief and LCD/pin proxy about optical Z; keep outer body and cage-hole coordinates fixed.",
                "parameters": baseline.PARAMS, "geometry_checks": checks, "print_validation": printed,
                "source_identity": {name: {"path": str(path.relative_to(ROOT)), "sha256": hashes[name]} for name, path in source_files.items()},
                "original_holder_byte_copy": sha(run / "holder.step") == hashes["holder_step"],
                "original_assembly_byte_copy": sha(assembly_path) == hashes["assembly_step"],
                "assembly_step": assembly_path.name,
                "limitations": ["No fit clearance, cage geometry or mounting-hole diameter was changed.",
                                "Assembly contains LCD and cage-rod references; use PRINT_THIS files to print only the holder.",
                                "The 45-degree pin channel meets a corner rod opening at the front face; the rear rod bore remains unchanged. Route external wires away from that rod."] if angle else
                               ["Exact accepted tolerance-adjusted geometry; the print copy is only translated onto Z=0."]}
        (run / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
        sources = run / "source"
        sources.mkdir(exist_ok=True)
        for name, path in source_files.items():
            target = sources / (name + path.suffix)
            if not target.exists():
                shutil.copy2(path, target)
        variants[key] = {"run_dir": str(run.relative_to(ROOT)), "manifest": str((run / "manifest.json").relative_to(ROOT)),
                         "assembly_step": str(assembly_path.relative_to(ROOT)), "print_validation": printed}
        shutil.copy2(assembly_path, DESIGN / f"USE_THIS_qyh1123_holder_{key}_assembly.step")
    for key, path in source_files.items():
        if sha(path) != hashes[key]:
            raise RuntimeError(f"Accepted source changed: {path}")
    summary = {"design": STEM, "variants": variants, "accepted_sources_unchanged": True}
    (ART / "seat45_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
