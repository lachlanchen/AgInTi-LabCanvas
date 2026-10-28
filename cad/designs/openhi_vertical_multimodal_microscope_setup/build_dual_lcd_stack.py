#!/usr/bin/env python3
"""Reassemble the photographed dual-GT/dual-LCD stack with frozen OpenHI relays."""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import cadquery as cq
import trimesh

import build_openhi_vertical_multimodal_microscope_setup as original

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(DESIGN.parent / "yxra100_servo_analyzer_breadboard_mount"))
from build_horizontal_cascade import compare_shapes, digest, parts_from_step, signature

BASE = DESIGN / "runs/run-2-vertical-cascade-full-frame-20261027T140302Z"
LCD = DESIGN.parent / "qyh1123_light_valve_centered_clearance_cage_holder" / "runs/run-4-45deg-full-through-pin-dupont-clearance-print-ready-20261028T120038Z"
VARIANTS = ("single_4f", "dual_4f", "dual_4f_vertical")
UPPER_NAMES = {"openhi_microscope", "polarizer_to_microscope_adapter",
               "primary_openhi_4f", "secondary_openhi_4f",
               "microscope_to_4f_adapter", "vertical_cascade_spacer"}
LAYERS = [
    {"name": "dock", "bottom_mm": 0.0, "top_mm": 30.0},
    {"name": "lamp_holder", "bottom_mm": 35.0, "top_mm": 43.0},
    {"name": "GT090101_lower", "bottom_mm": 48.0, "top_mm": 66.0},
    {"name": "LCD_holder_lower", "bottom_mm": 71.0, "top_mm": 79.0},
    {"name": "sample_holder_and_cap", "bottom_mm": 84.0, "top_mm": 118.0},
    {"name": "LCD_holder_upper", "bottom_mm": 123.0, "top_mm": 131.0},
    {"name": "GT090101_upper", "bottom_mm": 136.0, "top_mm": 154.0},
]
P = {"cage_pitch_mm": 30.0, "cage_rod_diameter_mm": 6.0,
     "spacer_height_mm": 5.0, "spacer_layer_bottoms_mm": [30, 43, 66, 79, 118, 131],
     "lcd_seat_angle_deg": 45.0, "microscope_bottom_z_mm": 162.0,
     "upper_apparatus_lift_mm": 22.0, "microscope_gap_above_GT_mm": 8.0,
     "axial_placement_is_measured": False}
LIMITATIONS = [
    "The photograph establishes the component order. The six 5 mm spacer layers are explicit layout assumptions, not axial measurements recovered from the photograph.",
    "Both accepted 45-degree LCD holders are shown populated with QYH1123 glass/pin references. Electrical operation, drive settings and polarizer angles are not inferred.",
    "Supplier GT090101, accepted fixture bodies and complete OpenHI relays are imported without geometry changes; only rigid placements change.",
    "Accepted relay datums and beam-splitter offsets are preserved. Objective-to-sample working distance, focus and sensor conjugates are not newly qualified.",
    "Frame/event camera housings, lamp envelope, film and sample are visualization references, not manufacturing models.",
    "This is the fixed/manual-polarizer apparatus. No motorized-stage acquisition or historical experimental result is claimed.",
    "Assembly STEP files are for review, not direct printing. Use the individual accepted component projects for manufacture.",
]


def upper(name):
    return name in UPPER_NAMES or name.startswith(("frame_camera_", "event_camera_", "c12880_"))


def make_lower():
    parts, evidence = {}, {}

    def add(name, shape, category, source=None, translation=(0, 0, 0)):
        placed = shape.translate(translation)
        parts[name] = (placed.val(), original.COLORS[category].toTuple()[:3])
        evidence[name] = {"source": str(source.relative_to(ROOT)) if source else "visualization reference",
                          "category": category, "translation_mm": list(translation),
                          "exact_source_geometry": bool(source)}

    src = original.SOURCE
    add("dock", original.import_step(src["dock"]), "polymer_mid", src["dock"])
    add("lamp_holder", original.import_step(src["lamp_holder"]), "polymer", src["lamp_holder"], (0, 0, 39))
    add("lamp_pcb", original.import_step(src["lamp_pcb"]), "pcb", src["lamp_pcb"], (0, 0, 39))
    for part in original.build_tungsten_bulb(39):
        add(part.name, part.shape, part.category)
    frozen_single = BASE / f"USE_THIS_{original.STEM}_single_4f.step"
    gt = cq.Workplane(obj=parts_from_step(frozen_single)["gt090101_polarizer"][0])
    gt_min = original.P["gt090101_bottom_z_mm"]
    for name, bottom in (("GT090101_lower", 48), ("GT090101_upper", 136)):
        add(name, gt, "polymer", frozen_single, (0, 0, bottom - gt_min))
        evidence[name]["source_component"] = "gt090101_polarizer"
    for position, center in (("lower", 75), ("upper", 127)):
        for suffix, file, category in (("holder", "holder.step", "polymer"),
                                       ("glass", "LCD_glass_reference.step", "glass"),
                                       ("pins", "rear_facing_pins_reference.step", "metal")):
            path = LCD / file
            add(f"LCD_{position}_{suffix}", original.import_step(path), category, path, (0, 0, center))
        film = original.box((18, 20, 0.25), (0, 0, center + 1.825))
        film = film.rotate((0, 0, 0), (0, 0, 1), 45)
        add(f"LCD_{position}_adhered_film", film, "polarizer")
    add("sample_holder_and_cap", original.import_step(src["sample_holder"]), "polymer_mid", src["sample_holder"], (0, 0, 84))
    for part in original.build_petri_and_sample(84):
        add(part.name, part.shape, part.category)
    spacer = original.import_step(src["spacer"])
    rod_xy = [(-15, -15), (-15, 15), (15, -15), (15, 15)]
    for i, (x, y) in enumerate(rod_xy, 1):
        for level, start, end in (("lower", 30, 90), ("upper", 112, 154)):
            add(f"cage_rod_{i}_{level}", original.z_cylinder(6, end - start, start), "metal", translation=(x, y, 0))
        for layer, bottom in enumerate(P["spacer_layer_bottoms_mm"], 1):
            add(f"spacer_L{layer}_{i}", spacer, "metal", src["spacer"], (x, y, bottom))
    return parts, evidence


def shifted_optical_contract(accepted):
    data = copy.deepcopy({key: accepted[key] for key in ("datums_mm", "secondary_4f", "detector_contract")})
    lift = P["upper_apparatus_lift_mm"]
    for key in data["datums_mm"]:
        if key.endswith("_z"):
            data["datums_mm"][key] += lift
    second = data["secondary_4f"]
    if second:
        second["beam_splitter_center_mm"][2] += lift
        for key in second:
            if key.endswith("_z_mm"):
                second[key] += lift
    paths = [copy.deepcopy(path) for path in accepted["optical_paths"] if path["name"] != "illumination"]
    for path in paths:
        for point in path["points"]:
            point[2] += lift
    data["optical_paths"] = [{"name": "illumination", "points": [[0, 0, 40], [0, 0, 162]], "color": "warm"}] + paths
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photo", type=Path)
    parser.add_argument("--run-name")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    existing = [int(match.group(1)) for path in (DESIGN / "runs").iterdir()
                if (match := re.match(r"run-(\d+)-", path.name))]
    name = args.run_name or f"run-{max(existing, default=0) + 1}-dual-lcd-dual-polarizer-all-relay-layouts-{stamp}"
    if Path(name).name != name:
        raise ValueError("Run name must be a single directory name")
    run = DESIGN / "runs" / name
    run.mkdir(parents=True, exist_ok=True)
    if (run / "manifest.json").exists():
        raise RuntimeError("Preserve completed runs; choose a new run name")
    inputs = {"accepted_manifest": BASE / "manifest.json"}
    for v in VARIANTS:
        inputs[v] = BASE / f"USE_THIS_{original.STEM}_{v}.step"
    for key in ("dock", "spacer", "lamp_holder", "lamp_pcb", "gt090101", "sample_holder"):
        inputs[key] = original.SOURCE[key]
    for file in ("holder.step", "LCD_glass_reference.step", "rear_facing_pins_reference.step"):
        inputs["lcd_" + file] = LCD / file
    hashes = {key: digest(path) for key, path in inputs.items()}
    accepted_manifest = json.loads(inputs["accepted_manifest"].read_text())
    lower, lower_evidence = make_lower()
    lower_overlap = {}
    for i, a in enumerate(LAYERS):
        for b in LAYERS[i + 1:]:
            if a["top_mm"] > b["bottom_mm"]:
                raise RuntimeError("The explicit axial layer envelopes overlap")
    for name in ("LCD_lower_pins", "LCD_upper_pins"):
        pin = lower[name][0]
        lower_overlap[name] = {}
        for other in ("LCD_lower_holder", "LCD_upper_holder", "GT090101_lower", "GT090101_upper", "sample_holder_and_cap"):
            common = pin.intersect(lower[other][0])
            volume = sum(s.Volume(1e-8) for s in common.Solids())
            lower_overlap[name][other] = volume
            if volume > 1e-5:
                raise RuntimeError(f"Pin interference: {name}/{other}: {volume}")
    results = {}
    for variant in VARIANTS:
        print(f"Building {variant}", flush=True)
        frozen = parts_from_step(inputs[variant])
        retained = {name: (shape.translate((0, 0, P["upper_apparatus_lift_mm"])), color)
                    for name, (shape, color) in frozen.items() if upper(name)}
        parts = {**lower, **retained}
        assembly = cq.Assembly(name=f"OpenHI_dual_LCD_stack_{variant}")
        meshes = run / "render_meshes" / variant
        meshes.mkdir(parents=True, exist_ok=True)
        records, render_components = [], []
        for name, (shape, color) in parts.items():
            color = color or (0.2, 0.23, 0.27)
            category = lower_evidence.get(name, {}).get("category", "polymer_mid")
            if name.startswith("frame_camera_"):
                category = "camera" if name.endswith("body") else "metal"
            elif name.startswith("event_camera_"):
                category = "event_camera" if name.endswith("body") else "metal"
            elif name.startswith("c12880_"):
                category = {"socket": "polymer", "plate": "polymer_mid", "board": "pcb", "sensor": "sensor", "pins": "metal"}[name.split("_")[-1]]
            elif name == "openhi_microscope":
                category = "metal"
            if name == "tungsten_bulb":
                color = (0.95, 0.65, 0.18)
            if name.startswith("event_camera_") and name.endswith("body"):
                color = (0.55, 0.16, 0.12)
            assembly.add(shape, name=name, color=cq.Color(*color))
            mesh = meshes / (name + ".stl")
            cq.exporters.export(shape, str(mesh), tolerance=0.06, angularTolerance=0.15)
            records.append({"name": name, "geometry": signature(shape),
                            "placement": lower_evidence.get(name, {"source": str(inputs[variant].relative_to(ROOT)),
                                                                  "translation_mm": [0, 0, P["upper_apparatus_lift_mm"]], "exact_source_geometry": True})})
            if name not in ("primary_openhi_4f", "secondary_openhi_4f"):
                render_components.append({"name": name, "mesh": str(mesh.relative_to(run)), "color": color, "category": category})
        # Retain accepted decomposed relay meshes so optical glass stays a separate material.
        for mesh_source in sorted((DESIGN / "artifacts/render_meshes" / variant).glob("*4f_*.stl")):
            shape = trimesh.load_mesh(mesh_source, process=False)
            shape.apply_translation((0, 0, P["upper_apparatus_lift_mm"]))
            target = meshes / mesh_source.name
            shape.export(target)
            category = "lens" if "lens_" in mesh_source.stem else "beam_splitter" if "beam_splitter_reference" in mesh_source.stem else "polymer_mid"
            render_components.append({"name": mesh_source.stem, "mesh": str(target.relative_to(run)),
                                      "category": category, "color": (0.22, 0.25, 0.28),
                                      "source_mesh": str(mesh_source.relative_to(ROOT)), "source_sha256": digest(mesh_source)})
        if not any(row["name"].startswith("primary_4f_") for row in render_components):
            raise RuntimeError("Missing accepted decomposed primary relay meshes")
        step = run / f"openhi_dual_lcd_stack_{variant}_assembly.step"
        assembly.save(str(step))
        imported = parts_from_step(step)
        if set(imported) != set(parts):
            raise RuntimeError("Named components lost during STEP export")
        checks = {name: compare_shapes(shape, imported[name][0]) for name, (shape, _) in parts.items()}
        preserved = {name: compare_shapes(shape, imported[name][0]) for name, (shape, _) in retained.items()}
        result = shifted_optical_contract(accepted_manifest["variants"][variant])
        result.update({"assembly_step": step.name, "components": records, "render_components": render_components,
                       "step_round_trip": checks, "preserved_upper_parts": preserved,
                       "all_step_round_trips_valid": True, "lower_detail_components": list(lower)})
        results[variant] = result
        print(f"Validated {variant}: {len(parts)} named components", flush=True)
    photo_record = None
    if args.photo:
        photo = run / "reference_media/current_dual_lcd_stack.jpeg"
        photo.parent.mkdir(exist_ok=True)
        shutil.copy2(args.photo, photo)
        photo_record = {"path": str(photo.relative_to(run)), "sha256": digest(photo),
                        "role": "component order and orientation, not an axial dimensional survey"}
    data = {"name": DESIGN.name, "run_name": run.name, "configuration": "fixed_dual_GT090101_dual_QYH1123_stack",
            "parameters": P, "axial_layers": LAYERS,
            "stack_sequence": ["dock", "lamp and PCB", "lower GT090101", "lower QYH1123 LCD holder", "sample holder, dish and cap", "upper QYH1123 LCD holder", "upper GT090101", "microscope", "relay(s) and detectors"],
            "photograph": photo_record, "source_identity": {key: {"path": str(path.relative_to(ROOT)), "sha256": hashes[key]} for key, path in inputs.items()},
            "lower_pin_intersections_mm3": lower_overlap, "variants": results, "limitations": LIMITATIONS,
            "detail_policy": "Lower detail hides microscope, relays and detectors without moving or exploding the shared lower stack."}
    (run / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    sources = run / "source"
    sources.mkdir(exist_ok=True)
    for file in (Path(__file__), DESIGN / "render_dual_lcd_stack.py", DESIGN / "package_dual_lcd_stack.py",
                 Path(original.__file__), DESIGN.parent / "yxra100_servo_analyzer_breadboard_mount/build_horizontal_cascade.py",
                 ROOT / "cad/tools/blender_camera_fit.py"):
        shutil.copy2(file, sources / file.name)
    for key, path in inputs.items():
        if digest(path) != hashes[key]:
            raise RuntimeError(f"Source was changed: {key}")
    summary = {"run_dir": str(run.relative_to(ROOT)), "manifest": str((run / "manifest.json").relative_to(ROOT)),
               "configuration": data["configuration"], "variants": list(VARIANTS)}
    (DESIGN / "artifacts/dual_lcd_stack_latest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
