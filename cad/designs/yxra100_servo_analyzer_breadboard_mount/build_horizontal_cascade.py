#!/usr/bin/env python3
"""Assemble frozen run-2 B-reps into the horizontal two-relay apparatus."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepTools import BRepTools


DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
BASE_RUN = DESIGN / "runs/run-2-square-y-motor-yoke-m3-bridge-20261027T145017Z"
RELAY_RUN = DESIGN.parent / "openhi_vertical_multimodal_microscope_setup/runs/run-2-vertical-cascade-full-frame-20261027T140302Z"
RUN_NAME = "run-3-horizontal-dual-4f-rotary-analyzer-20261027T163343Z"
RUN = DESIGN / "runs" / RUN_NAME
ART = DESIGN / "artifacts"
STEM = "yxra100_rotary_analyzer_horizontal_dual_4f_assembly"
BASE_STEP = BASE_RUN / "USE_THIS_yxra100_servo_analyzer_breadboard_mount_assembly.step"
RELAY_STEP = RELAY_RUN / "USE_THIS_openhi_vertical_multimodal_microscope_setup_dual_4f.step"
LOWER_NAMES = {
    "dock", "lamp_holder", "lamp_pcb", "tungsten_bulb", "tungsten_bulb_leads",
    "lcd_holder", "qyh1123_lcd", "lcd_lower_polarizer", "sample_holder_and_cap",
    "petri_dish", "sample_volume",
}
LIMITATIONS = [
    "Proposed motorized apparatus layout; the earlier four-angle measurements did not use motorized rotation.",
    "No firmware, raw measurements, reconstruction, Windows manuscript, stage motion or acquisition was changed.",
    "Accepted relay geometry, lens seats, threads and optical datums are reused, not redesigned or optically recalibrated.",
    "The existing microscope lift and objective-free gap are preserved; focus, conjugate planes and working distance remain unvalidated.",
    "Frame/event camera bodies and existing interface/sample proxies are illustrative, not supplier-complete devices.",
    "The rotary fixture remains a fit/clearance prototype requiring physical load, thermal, cable and fastening checks.",
    "The lower-stack detail intentionally hides the rotary hardware and upper apparatus; it is not a literal crop or alternate physical assembly.",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parts_from_step(path):
    parts = {}
    for shape, label, loc, color in cq.Assembly.load(str(path)):
        name = label.rsplit("/", 1)[-1]
        if name in parts:
            raise RuntimeError(f"Duplicate source component: {name}")
        parts[name] = (shape.moved(loc), color.toTuple()[:3] if color else None)
    return parts


def signature(shape):
    # Display tessellation can fail mesh checks on valid imported B-reps.
    # Discard only that cache; no analytic geometry or topology is repaired.
    BRepTools.Clean_s(shape.wrapped)
    bb = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, bb, False, False)
    return {
        "solids": len(shape.Solids()), "shells": len(shape.Shells()),
        "faces": len(shape.Faces()), "valid": shape.isValid(),
        "closed_solids_valid": all(s.isValid() for s in shape.Solids()),
        "volume_mm3": sum(s.Volume(1e-8) for s in shape.Solids()),
        "bounds_mm": list(bb.Get()),
    }


def compare_shapes(expected, actual):
    a, b = signature(expected), signature(actual)
    error = max(abs(x - y) for x, y in zip(a["bounds_mm"], b["bounds_mm"]))
    volume_error = abs(a["volume_mm3"] - b["volume_mm3"])
    ok = (a["closed_solids_valid"] and b["closed_solids_valid"]
          and a["valid"] and b["valid"] and error < 1e-4
          and volume_error < max(1e-4, abs(a["volume_mm3"]) * 1e-7)
          and all(a[k] == b[k] for k in ("solids", "shells", "faces")))
    if not ok:
        raise RuntimeError(f"Geometry changed: {a} vs {b}")
    return {"bounds_max_error_mm": error, "volume_error_mm3": volume_error,
            "solid_shell_face_counts_match": True, "valid": True,
            "source_compound_valid": a["valid"], "exported_closed_solids_valid": b["closed_solids_valid"]}


def intersection_volume(a, b):
    x, y = a.BoundingBox(), b.BoundingBox()
    if any(getattr(x, f"{axis}max") <= getattr(y, f"{axis}min") + 1e-5
           or getattr(y, f"{axis}max") <= getattr(x, f"{axis}min") + 1e-5
           for axis in "xyz"):
        return 0.0
    return sum(s.Volume() for s in a.intersect(b).Solids())


def main():
    inputs = {"rotary_run_2": BASE_STEP, "horizontal_relay_run_2": RELAY_STEP,
              "rotary_manifest": BASE_RUN / "manifest.json", "relay_manifest": RELAY_RUN / "manifest.json"}
    source_hashes = {key: digest(path) for key, path in inputs.items()}
    base = parts_from_step(BASE_STEP)
    relay = parts_from_step(RELAY_STEP)
    original = json.loads(inputs["rotary_manifest"].read_text())
    relay_manifest = json.loads(inputs["relay_manifest"].read_text())
    accepted = relay_manifest["variants"]["dual_4f"]
    lift = original["optical_constraints"]["required_microscope_upshift_mm"]
    compare_shapes(relay["primary_openhi_4f"][0].translate((0, 0, lift)), base["primary_openhi_4f"][0])

    # Reuse every base component except the spectrometer now moved downstream.
    retained = {name: value for name, value in base.items() if not name.startswith("c12880_")}
    new_names = {name for name in relay if name == "secondary_openhi_4f"
                 or name.startswith(("c12880_", "event_camera_"))}
    if len(new_names) != 8 or accepted["secondary_4f"]["rotation_y_deg"] != 90:
        raise RuntimeError("Expected the accepted lateral cascade with three detectors")
    parts = dict(retained)
    for name in sorted(new_names):
        shape, color = relay[name]
        parts[name] = (shape.translate((0, 0, lift)), color)

    max_overlap = max(intersection_volume(parts[name][0], value[0])
                      for name in new_names for value in retained.values())
    if max_overlap > 0.01:
        raise RuntimeError(f"New relay/detector interferes with accepted apparatus: {max_overlap}")
    RUN.mkdir(parents=True, exist_ok=True)
    mesh_dir = RUN / "render_meshes"
    mesh_dir.mkdir(exist_ok=True)
    colors = {row["name"]: row["color"] for row in original["render_components"]}
    assembly = cq.Assembly(name="YXRA100_horizontal_two_4f_analyzer_apparatus")
    components = []
    for name, (shape, color) in parts.items():
        color = colors.get(name, color) or (0.22, 0.25, 0.28)
        if name.startswith("event_camera_"):
            color = (0.55, 0.16, 0.12) if name.endswith("body") else (0.55, 0.58, 0.61)
        assembly.add(shape, name=name, color=cq.Color(*color))
        mesh = mesh_dir / f"{name}.stl"
        cq.exporters.export(shape, str(mesh), tolerance=0.06, angularTolerance=0.15)
        components.append({"name": name, "mesh": f"render_meshes/{name}.stl", "color": color,
                           "origin": "rotary_run_2" if name in retained else "horizontal_relay_run_2",
                           "source_translation_mm": [0, 0, 0 if name in retained else lift],
                           "geometry": signature(shape)})
    assembly_path = RUN / f"{STEM}.step"
    assembly.save(str(assembly_path))
    back = parts_from_step(assembly_path)
    if set(back) != set(parts):
        raise RuntimeError("STEP round trip lost named assembly components")
    round_trip = {name: compare_shapes(value[0], back[name][0]) for name, value in parts.items()}
    preserved = {name: compare_shapes(base[name][0], back[name][0]) for name in retained}
    lower_names = sorted(name for name in retained if name in LOWER_NAMES or name.startswith("spacer_") or name.endswith("_lower"))

    datums = copy.deepcopy(accepted["datums_mm"])
    for key in datums:
        if key.endswith("_z"):
            datums[key] = round(datums[key] + lift, 6)
    secondary = copy.deepcopy(accepted["secondary_4f"])
    secondary["beam_splitter_center_mm"][2] = round(secondary["beam_splitter_center_mm"][2] + lift, 6)
    secondary["c_output_z_mm"] = round(secondary["c_output_z_mm"] + lift, 6)
    gap = secondary["a_input_x_mm"] - datums["primary_c_output_x"]
    if abs(gap - 3) > 1e-6 or secondary["rotation_y_deg"] != 90:
        raise RuntimeError("Horizontal cascade input datum differs from accepted layout")

    data = copy.deepcopy(original)
    data.update({
        "run_name": RUN_NAME, "configuration": "horizontal_dual_4f_rotary_analyzer",
        "status": "CAD and publication-view update; not an acquisition or optical-performance validation",
        "render_components": components,
        "assembly_step": assembly_path.name,
        "assembly_step_round_trip_valid": True,
        "frozen_sources": {key: {"path": str(path.relative_to(ROOT)), "sha256": source_hashes[key]} for key, path in inputs.items()},
        "cascade": {"source_variant": "dual_4f", "vertical_cascade": False,
                    "existing_microscope_lift_mm": lift, "additional_relay_redesign": False,
                    "datums_mm": datums, "secondary_4f": secondary, "interface_gap_mm": gap,
                    "detector_contract": accepted["detector_contract"],
                    "source_b_axis_shift_mm": relay_manifest["parameters"]["openhi_source_b_axis_shift_mm"]},
        "preserved_base_components": preserved,
        "step_component_round_trip": round_trip,
        "new_components": sorted(new_names),
        "new_vs_retained_max_interference_mm3": max_overlap,
        "detail_view": {"type": "explanatory visibility-only detail", "geometry_transform": "none",
                        "included_components": lower_names,
                        "omitted_components": sorted(set(parts) - set(lower_names)),
                        "label": "Shared lower optical stack; rotary hardware and upper apparatus hidden"},
        "historical_measurements_motorized": False,
        "limitations": LIMITATIONS,
    })
    (RUN / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    for key, path in inputs.items():
        if digest(path) != source_hashes[key]:
            raise RuntimeError(f"Archived input was changed: {key}")
    ART.mkdir(exist_ok=True)
    shutil.copy2(assembly_path, ART / assembly_path.name)
    shutil.copy2(assembly_path, DESIGN / f"USE_THIS_{STEM}.step")
    shutil.copy2(assembly_path, DESIGN / "USE_THIS_yxra100_servo_analyzer_breadboard_mount_assembly.step")
    shutil.copy2(RUN / "manifest.json", ART / "manifest.json")
    print(json.dumps({"run": str(RUN), "preserved_components": len(preserved),
                      "total_components": len(parts), "cascade_gap_mm": gap,
                      "new_interference_mm3": max_overlap}, indent=2))


if __name__ == "__main__":
    main()
