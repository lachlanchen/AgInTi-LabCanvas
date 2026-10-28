#!/usr/bin/env python3
"""Open one generous pin/plug window through the accepted QYH1123 holders."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import cadquery as cq

import build_seat45_handoff as accepted

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
ART = DESIGN / "artifacts"
STAMP = "20261028T120038Z"
RUNS = {
    "0deg": DESIGN / "runs" / f"run-3-0deg-full-through-pin-dupont-clearance-print-ready-{STAMP}",
    "45deg": DESIGN / "runs" / f"run-4-45deg-full-through-pin-dupont-clearance-print-ready-{STAMP}",
}
NUTSTORE = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
P = {"window_width_mm": 12.0, "window_length_mm": 9.0, "window_center_y_mm": -12.0,
     "window_inner_y_mm": -7.5, "window_outer_y_mm": -16.5,
     "body_thickness_mm": 8.0, "optical_window_edge_y_mm": -6.5,
     "remaining_optical_ledge_mm": 1.0,
     "illustrative_plug_envelope_width_mm": 6.0, "illustrative_plug_envelope_length_mm": 4.0,
     "illustrative_plug_envelope_depth_mm": 10.0, "illustrative_pin_row_y_mm": -9.8}


def rotate(shape, angle):
    return shape.rotate((0, 0, 0), (0, 0, 1), angle)


def box(size, center):
    return accepted.baseline.z_box(size, center)


def wiring_references(angle):
    p = accepted.baseline.PARAMS
    glass_back = p["body_thickness_mm"] / 2 - p["valve_pocket_depth_mm"] + 0.18
    glass_center = glass_back + p["valve_thickness_mm"] / 2
    glass = box((p["valve_outer_width_mm"], p["valve_outer_height_mm"], p["valve_thickness_mm"]), (0, 0, glass_center))
    glass = glass.union(box((15, 15, 0.18), (0, 0, glass_center + 1.1)))
    pins = []
    for x in (-p["pin_pitch_mm"] / 2, p["pin_pitch_mm"] / 2):
        pins.append(box((p["pin_width_mm"], p["pin_thickness_mm"], p["pin_length_mm"]),
                        (x, P["illustrative_pin_row_y_mm"], glass_back - p["pin_length_mm"] / 2)).val())
    pins = cq.Workplane(obj=cq.Compound.makeCompound(pins))
    # A clearance envelope, not a measured connector model or a printed part.
    plug_top = glass_back - 0.5
    envelope = box((6, 4, 10), (0, P["illustrative_pin_row_y_mm"], plug_top - 5))
    return {"LCD_glass_reference": rotate(glass, angle), "rear_facing_pins_reference": rotate(pins, angle),
            "illustrative_Dupont_clearance_envelope": rotate(envelope, angle)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    for path in args.references:
        if not path.is_file():
            raise FileNotFoundError(path)
    variants = {}
    for key, angle in (("0deg", 0), ("45deg", 45)):
        source_run = accepted.RUNS[key]
        source_path = source_run / "holder.step"
        source_hash = accepted.sha(source_path)
        before = cq.importers.importStep(str(source_path))
        cutter = rotate(box((P["window_width_mm"], P["window_length_mm"], 10),
                            (0, P["window_center_y_mm"], 0)), angle)
        holder = before.cut(cutter)
        run = RUNS[key]
        run.mkdir(parents=True, exist_ok=True)
        checks = {"full_window_obstruction_mm3": accepted.volume(holder.intersect(cutter)),
                  "material_added_mm3": accepted.volume(holder.cut(before)),
                  "outside_window_changed_mm3": accepted.changed_volume(before.cut(cutter), holder.cut(cutter)),
                  "protected_cage_collars_changed_mm3": 0.0,
                  "holder_solid_count": len(holder.solids().vals()), "holder_valid": accepted.valid(holder)}
        for x in (-15, 15):
            for y in (-15, 15):
                collar = accepted.baseline.z_cylinder(8.4, 10, -5).translate((x, y, 0))
                checks["protected_cage_collars_changed_mm3"] += accepted.changed_volume(before.intersect(collar), holder.intersect(collar))
        refs = wiring_references(angle)
        checks["pin_envelope_obstruction_mm3"] = accepted.volume(holder.intersect(refs["rear_facing_pins_reference"]))
        checks["plug_envelope_obstruction_mm3"] = accepted.volume(holder.intersect(refs["illustrative_Dupont_clearance_envelope"]))
        rods = cq.importers.importStep(str(source_run / "rods_proxy.step"))
        checks["pins_vs_rods_mm3"] = accepted.volume(refs["rear_facing_pins_reference"].intersect(rods))
        checks["plug_vs_rods_mm3"] = accepted.volume(refs["illustrative_Dupont_clearance_envelope"].intersect(rods))
        if not (checks["holder_valid"] and checks["holder_solid_count"] == 1
                and all(value < 1e-5 for name, value in checks.items() if name.endswith("_mm3"))):
            raise RuntimeError(f"Pin clearance invalid: {key}: {checks}")
        assembly = cq.Assembly(name=f"QYH1123_{key}_full_through_pin_clearance")
        parts = {"holder": holder, **refs, "cage_rods_reference": rods}
        colors = {"holder": (0.22, 0.34, 0.40), "LCD_glass_reference": (0.25, 0.7, 0.8),
                  "rear_facing_pins_reference": (0.85, 0.65, 0.25),
                  "illustrative_Dupont_clearance_envelope": (0.65, 0.36, 0.12), "cage_rods_reference": (0.65, 0.7, 0.75)}
        for name, shape in parts.items():
            assembly.add(shape, name=name, color=cq.Color(*colors[name]))
            for suffix in ("step", "stl"):
                cq.exporters.export(shape, str(run / f"{name}.{suffix}"))
        assembly_path = run / f"qyh1123_full_pin_clearance_{key}_assembly.step"
        assembly.save(str(assembly_path))
        back = cq.importers.importStep(str(run / "holder.step"))
        checks["round_trip_changed_mm3"] = accepted.changed_volume(holder, back)
        checks["assembly_valid"] = accepted.valid(cq.importers.importStep(str(assembly_path)))
        if checks["round_trip_changed_mm3"] > 1e-5 or not checks["assembly_valid"]:
            raise RuntimeError("Exported STEP did not retain valid clearance geometry")
        printed = accepted.export_print(holder, run, key + "_full_pin_clearance")
        sources = run / "source"
        sources.mkdir(exist_ok=True)
        shutil.copy2(source_path, sources / "accepted_holder.step")
        for path in (Path(__file__), DESIGN / "build_seat45_handoff.py", accepted.SOURCE_SCRIPT,
                     DESIGN / "render_pin_clearance_handoff.py", ROOT / "cad/tools/simple_3mf.py", ROOT / "cad/tools/blender_camera_fit.py"):
            shutil.copy2(path, sources / path.name)
        photo_records = []
        for index, path in enumerate(args.references, 1):
            target = run / "reference_photos" / f"lcd_reference_{index:02d}{path.suffix.lower()}"
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(path, target)
            photo_records.append({"file": str(target.relative_to(run)), "sha256": accepted.sha(target)})
        data = {"design": DESIGN.name, "variant": key, "seat_rotation_deg": angle, "run_name": run.name,
                "source": {"path": str(source_path.relative_to(ROOT)), "sha256": source_hash},
                "parameters": accepted.baseline.PARAMS, "pin_clearance": P,
                "coordinate_rule": "Pocket face +Z; LCD and pin feature coordinates are local XY, then rotated about optical Z. Pins/plug can route toward rear -Z.",
                "geometry_checks": checks, "print_validation": printed, "assembly_step": assembly_path.name,
                "render_parts": [{"name": name, "mesh": name + ".stl", "color": colors[name]} for name in parts],
                "reference_photos": photo_records,
                "limitations": ["The 12 x 9 mm opening is fully through the 8 mm holder; no center bridge or blind floor remains beneath the pin/plug region.",
                                "LCD sink dimensions, optical window, outer body and cage-bore collars are retained from the accepted source.",
                                "The 6 x 4 x 10 mm plug envelope and rear-facing pin layout are illustrative clearance references, not measured Dupont connector specifications.",
                                "The holder stays 8 mm thick. Longer pins, plug housings and wires may project beyond the rear face; this is not a closed flush connector enclosure."]}
        (run / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
        if accepted.sha(source_path) != source_hash:
            raise RuntimeError("Accepted source was altered")
        shutil.copy2(assembly_path, DESIGN / f"USE_THIS_qyh1123_full_pin_clearance_{key}_assembly.step")
        variants[key] = {"run_dir": str(run.relative_to(ROOT)), "manifest": str((run / "manifest.json").relative_to(ROOT))}
    summary = {"variants": variants, "pin_clearance": P}
    (ART / "pin_clearance_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    subprocess.run(["blender", "--background", "--threads", "6", "--python-exit-code", "1", "--python",
                    str(DESIGN / "render_pin_clearance_handoff.py")], check=True)
    for key, row in variants.items():
        run = ROOT / row["run_dir"]
        data = json.loads((run / "manifest.json").read_text())
        (run / "README.md").write_text(
            f"# QYH1123 {key}: full pin and Dupont clearance\n\n"
            "One connected 12 x 9 mm window runs completely through the holder below both terminals and the space between them.\n"
            "In local LCD coordinates it spans x=-6..6 and y=-16.5..-7.5 mm. The 45-degree version rotates this window with the LCD seat.\n"
            "The opening retains a 1 mm ledge next to the optical through-window; all four cage bores and their surrounding material remain unchanged.\n"
            "The outer body remains 42 x 42 x 8 mm, the LCD pocket retains its accepted fit allowance, and no other geometry is rebuilt.\n\n"
            f"Print `{data['print_validation']['stem']}.3mf` (or the equivalent STEP/STL); only the holder is included.\n"
            f"`{data['assembly_step']}` contains separate illustrative LCD/pin/plug/rod references for inspection.\n\n"
            "Pins and the generic plug envelope are shown facing the rear. Connector and wire lengths may extend below the 8 mm body.\n"
            "Reference housings are not supplier CAD; the empty 12 x 9 mm through-region is the actual clearance contract.\n")
        camera_rows = json.loads((run / "renders/camera_validation.json").read_text())
        if len(camera_rows) != 4:
            raise RuntimeError("Missing front, rear, connector or print render")
        for row in camera_rows:
            b = row["projected_bounds"]
            if not (0.079 <= b["xmin"] < b["xmax"] <= 0.921 and 0.079 <= b["ymin"] < b["ymax"] <= 0.921):
                raise RuntimeError("Render violates safe framing")
        target = NUTSTORE / DESIGN.name / run.name
        records = {}
        for source in sorted(run.rglob("*")):
            if not source.is_file() or source.name == "sync_manifest.json":
                continue
            relative = source.relative_to(run)
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
            records[str(relative)] = accepted.sha(source)
            if accepted.sha(output) != records[str(relative)]:
                raise RuntimeError(f"Nutstore copy mismatch: {relative}")
        (run / "sync_manifest.json").write_text(json.dumps(records, indent=2) + "\n")
        shutil.copy2(run / "sync_manifest.json", target / "sync_manifest.json")
        assembly_path = run / data["assembly_step"]
        shutil.copy2(assembly_path, NUTSTORE / f"USE_THIS_qyh1123_full_pin_clearance_{key}_assembly.step")
        print(json.dumps({"variant": key, "nutstore": str(target), "verified_files": len(records) + 1}, indent=2))


if __name__ == "__main__":
    main()
