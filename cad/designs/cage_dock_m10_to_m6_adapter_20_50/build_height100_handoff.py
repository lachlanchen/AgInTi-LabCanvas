#!/usr/bin/env python3
"""Extend the original 9.8/6.0 mm dock adapter to 100 mm without scaling."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import cadquery as cq
import trimesh
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepTools import BRepTools

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
ART = DESIGN / "artifacts"
RUN = DESIGN / "runs/run-4-original-fit-plus30mm-height100-print-ready-20261028T071232Z"
NUTSTORE = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
TARGET = NUTSTORE / DESIGN.name / RUN.name
SOURCE = ART / "cage_dock_m10_to_m6_adapter_20_50.step"
SOURCE_SCRIPT = DESIGN / "build_cage_dock_m10_to_m6_adapter_20_50.py"
STEM = "cage_dock_adapter_d9p8_to_d6p0_h100"
sys.path.insert(0, str(ROOT / "cad/tools"))
from simple_3mf import export_stl_as_3mf


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def volume(shape):
    return sum(s.Volume(1e-8) for s in shape.solids().vals())


def difference(a, b):
    return volume(a.cut(b)) + volume(b.cut(a))


def region(z0, z1):
    return cq.Workplane("XY").box(40, 40, z1 - z0).translate((0, 0, (z0 + z1) / 2))


def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.val().wrapped, box, False, False)
    return list(box.Get())


def validate_print(path, count):
    back = cq.importers.importStep(str(path.with_suffix(".step")))
    BRepTools.Clean_s(back.val().wrapped)
    mesh = trimesh.load_mesh(path.with_suffix(".stl"), force="mesh")
    components = mesh.split(only_watertight=False)
    first_layers = [part.section(plane_origin=(0, 0, 0.2), plane_normal=(0, 0, 1)) is not None for part in components]
    with zipfile.ZipFile(path.with_suffix(".3mf")) as archive:
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    record = {"step_valid": back.val().isValid(), "solid_count": len(back.solids().vals()),
              "bounds_mm": bounds(back), "watertight": mesh.is_watertight,
              "mesh_components": len(components), "min_z_each_part_mm": [float(p.bounds[0, 2]) for p in components],
              "first_layer_nonempty_each_part": first_layers,
              "three_mf_build_items": len(model.findall("m:build/m:item", ns)),
              "three_mf_units": model.attrib["unit"], "stem": path.name}
    if not (record["step_valid"] and record["solid_count"] == count and record["watertight"]
            and record["mesh_components"] == count and all(first_layers)
            and all(abs(z) < 1e-6 for z in record["min_z_each_part_mm"])
            and record["three_mf_build_items"] == 1 and record["three_mf_units"] == "millimeter"):
        raise RuntimeError(f"Invalid print package: {record}")
    return record


def main():
    source_hash = sha(SOURCE)
    script_hash = sha(SOURCE_SCRIPT)
    spec = importlib.util.spec_from_file_location("original_dock_adapter", SOURCE_SCRIPT)
    original_builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original_builder)
    original = cq.importers.importStep(str(SOURCE))
    reconstruction_error = difference(original, original_builder.build_adapter())
    if reconstruction_error > 1e-5:
        raise RuntimeError("The original generator no longer matches the selected STEP")
    previous = copy.deepcopy(original_builder.PARAMS)
    original_builder.PARAMS["upper_rod_length_mm"] = 80.0
    original_builder.PARAMS["total_height_mm"] = 100.0
    rod = original_builder.build_adapter()
    lower_error = difference(original.intersect(region(-1, 20)), rod.intersect(region(-1, 20)))
    tip_error = difference(original.intersect(region(69, 71)), rod.intersect(region(99, 101)).translate((0, 0, -30)))
    delta = volume(rod) - volume(original)
    expected_delta = math.pi * 3.0 ** 2 * 30.0
    if lower_error > 1e-5 or tip_error > 1e-5 or abs(delta - expected_delta) > 1e-5:
        raise RuntimeError("The extension changed more than the shaft length")
    RUN.mkdir(parents=True, exist_ok=True)
    packages = {}
    for name, count in (("single", 1), ("2x2", 4)):
        model = rod
        centers = [[0.0, 0.0]]
        if count == 4:
            centers = [[x, y] for x in (-12.0, 12.0) for y in (-12.0, 12.0)]
            model = cq.Workplane(obj=cq.Compound.makeCompound([rod.val().translate((x, y, 0)) for x, y in centers]))
        path = RUN / f"PRINT_THIS_{STEM}_{name}"
        for suffix in ("step", "stl"):
            cq.exporters.export(model, str(path.with_suffix("." + suffix)), tolerance=0.015, angularTolerance=0.10)
        export_stl_as_3mf(path.with_suffix(".stl"), path.with_suffix(".3mf"), title=path.name)
        packages[name] = {"centers_mm": centers, **validate_print(path, count)}
    final = RUN / f"{STEM}_assembly.step"
    assembly = cq.Assembly(name="Four_100mm_original_fit_dock_adapters")
    for index, (x, y) in enumerate(packages["2x2"]["centers_mm"], 1):
        assembly.add(rod.translate((x, y, 0)), name=f"adapter_{index}", color=cq.Color(0.22, 0.42, 0.49))
    assembly.save(str(final))
    imported = cq.importers.importStep(str(final))
    if not imported.val().isValid() or len(imported.solids().vals()) != 4:
        raise RuntimeError("Named four-part assembly STEP failed validation")
    data = {"design": DESIGN.name, "run_name": RUN.name, "stem": STEM,
            "selected_baseline": "original 9.8 mm insert / nominal 6.0 mm shaft, not the later 6.3/6.4/6.5 mm variants",
            "parameters_mm": {"lower_diameter": 9.8, "lower_length": 20.0, "upper_diameter": 6.0,
                              "upper_length": 80.0, "total_height": 100.0, "added_upper_length": 30.0,
                              "bottom_chamfer": 0.35, "top_chamfer": 0.35, "grid_pitch": 24.0},
            "previous_parameters": previous,
            "source": {"path": str(SOURCE.relative_to(ROOT)), "sha256": source_hash,
                       "generator": str(SOURCE_SCRIPT.relative_to(ROOT)), "generator_sha256": script_hash},
            "geometry_checks": {"baseline_reconstruction_difference_mm3": reconstruction_error,
                                "lower_insert_difference_mm3": lower_error, "translated_top_difference_mm3": tip_error,
                                "added_volume_mm3": delta, "expected_added_volume_mm3": expected_delta},
            "print_packages": packages, "assembly_step": final.name,
            "limitations": ["The shaft remains nominal 6.0 mm in CAD; no compensation was inferred from the measured approximately 5.8 mm printed rod.",
                            "Smooth rods: no new threads or M3 holes were added.",
                            "Print upright on the wider lower end; the taller shafts may benefit from a slicer brim and conservative print speed."]}
    (RUN / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    (ART / "height100_manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    subprocess.run(["blender", "--background", "--threads", "6", "--python-exit-code", "1", "--python",
                    str(DESIGN / "render_height100_handoff.py")], check=True)
    cameras = json.loads((RUN / "renders/camera_validation.json").read_text())
    if {r["file"] for r in cameras} != {"single_100mm.png", "print_grid_2x2_100mm.png"}:
        raise RuntimeError("Missing checked single/grid renders")
    (RUN / "README.md").write_text(
        "# Dock adapter: 100 mm total height\n\n"
        "Original-fit extension: lower insert diameter 9.8 mm x 20 mm; upper shaft diameter 6.0 mm x 80 mm.\n"
        "Only the upper shaft gained 30 mm. Both 0.35 mm end chamfers, the lower insert and all diameters are preserved.\n"
        "The source is the original 70 mm model, not the later larger-shaft variants. No threads or pilot holes were added.\n\n"
        "Use PRINT_THIS files for printing: single prints one adapter; 2x2 prints four upright adapters at the original 24 mm pitch.\n"
        "Each option includes STEP, STL and 3MF. Each intended part is grounded at Z=0 with a verified first layer.\n"
        "The named assembly STEP contains the same four adapters for editing. Render previews show the exact print files.\n\n"
        "Use an optional slicer brim and conservative speed for the taller slender posts. Printed diameter can differ from nominal CAD diameter.\n")
    sources = RUN / "source"
    sources.mkdir(exist_ok=True)
    for source in (SOURCE, SOURCE_SCRIPT, Path(__file__), DESIGN / "render_height100_handoff.py",
                   ROOT / "cad/tools/simple_3mf.py", ROOT / "cad/tools/blender_camera_fit.py"):
        shutil.copy2(source, sources / source.name)
    if sha(SOURCE) != source_hash or sha(SOURCE_SCRIPT) != script_hash:
        raise RuntimeError("The selected original source changed")
    TARGET.mkdir(parents=True, exist_ok=True)
    synced = {}
    for source in sorted(RUN.rglob("*")):
        if not source.is_file() or source.name == "sync_manifest.json":
            continue
        relative = source.relative_to(RUN)
        target = TARGET / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha(source) != sha(target):
            raise RuntimeError(f"Nutstore copy mismatch: {relative}")
        synced[str(relative)] = sha(source)
    (RUN / "sync_manifest.json").write_text(json.dumps(synced, indent=2) + "\n")
    shutil.copy2(RUN / "sync_manifest.json", TARGET / "sync_manifest.json")
    for target in (DESIGN / f"USE_THIS_{STEM}_assembly.step", NUTSTORE / f"USE_THIS_{STEM}_assembly.step"):
        shutil.copy2(final, target)
        if sha(final) != sha(target):
            raise RuntimeError("Final assembly copy mismatch")
    print(json.dumps({"run_dir": str(RUN), "nutstore": str(TARGET), "parameters_mm": data["parameters_mm"],
                      "verified_files": len(synced) + 1}, indent=2))


if __name__ == "__main__":
    main()
